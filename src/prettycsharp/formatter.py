"""The formatting pipeline: parse, rewrite, print, then verify.

``format_source`` refuses input that does not parse (``CSharpSyntaxError``)
and raises ``FormattingError`` rather than return output that the verifier
finds different in meaning from the input. Formatting runs in a worker
thread with a large stack, so a deeply nested file fails cleanly instead of
crashing the interpreter.
"""

from __future__ import annotations

import dataclasses
import functools
import sys
import threading
from collections.abc import Callable, Iterable
from typing import TypeVar

from prettycsharp import conditional
from prettycsharp.isolate import isolate
from prettycsharp.parsing import CSharpSyntaxError, parse
from prettycsharp.printer import print_file
from prettycsharp.rewrites import rewrite
from prettycsharp.settings import Settings
from prettycsharp.syntax import SourceFile, build
from prettycsharp.verify import VerificationError, canonical, comment_words

LATEST = 99.0
# 255 MiB: Windows refuses a thread stack of 256 MiB or more.
_STACK_SIZE = 255 * 1024 * 1024
_RECURSION_LIMIT = 50_000
_lock = threading.Lock()

T = TypeVar("T")


class FormattingError(Exception):
    """The formatter could not produce output it can stand behind."""


def lang_version_of(settings: Settings, detected: float | None = None) -> float:
    if settings.lang_version == "auto":
        return detected if detected is not None else LATEST
    if settings.lang_version == "latest":
        return LATEST
    return float(settings.lang_version)


@dataclasses.dataclass(frozen=True)
class FormatResult:
    text: str
    # Lines (1-based, in the source) left as written because the parser could
    # not read them; only with syntax_errors = "format_around".
    kept_lines: tuple[int, ...] = ()


def format_source(source: str, settings: Settings | None = None, *, lang_version: float | None = None) -> str:
    """Return ``source`` formatted.

    Raises CSharpSyntaxError when the source does not parse, and
    FormattingError when the result fails the formatter's own check.
    ``lang_version`` is the project's C# version, used when the settings say
    ``auto``; without it the latest version is assumed.
    """
    return format_details(source, settings, lang_version=lang_version).text


def format_details(
    source: str, settings: Settings | None = None, *, lang_version: float | None = None
) -> FormatResult:
    """Like format_source, also telling which lines were left as written."""
    chosen = settings or Settings()
    version = lang_version_of(chosen, lang_version)
    return _run_with_big_stack(lambda: _format(source, chosen, version))


def _format(source: str, settings: Settings, lang_version: float) -> FormatResult:
    try:
        return FormatResult(_format_parsed(source, settings, lang_version))
    except CSharpSyntaxError as error:
        syntax_error = error
    # Neither rewrite may move a namespace's braces across hidden lines.
    hiding = dataclasses.replace(settings, namespace_style="preserve")
    around = settings.syntax_errors == "format_around"
    if conditional.has_conditionals(source):
        # The #if branches together are not valid C#: format one view at a time,
        # and with format_around, within a view, around the lines it cannot read.
        kept: list[str] = []
        try:
            result = conditional.format_conditional(
                source,
                functools.partial(_format_view, settings=hiding, lang_version=lang_version, around=around, kept=kept),
                functools.partial(_same_view, around=around),
                _usable_around if around else conditional.parses,
                tight=settings.directive_blank_lines == "remove",
            )
        except conditional.BranchChanged as error:
            raise FormattingError(str(error)) from None
        except conditional.ConditionalError:
            raise syntax_error from None
        if result is not None:
            return FormatResult(result, _source_rows(source, kept))
    if around:
        whole = _format_around(source, hiding, lang_version)
        if whole is not None:
            return whole
    raise syntax_error


def _format_view(text: str, *, settings: Settings, lang_version: float, around: bool, kept: list[str]) -> str:
    """Format one view of an #if-split file, around unreadable lines if allowed."""
    try:
        return _format_parsed(text, settings, lang_version)
    except CSharpSyntaxError:
        if not around:
            raise
    masked = isolate(text)
    if masked is None:
        raise CSharpSyntaxError(1, 1)
    formatted = _format_parsed(masked.text, settings, lang_version)
    if _placements(masked.text) != _placements(formatted):
        raise FormattingError("a line the parser cannot read would move")
    kept.extend(masked.hidden.values())
    return conditional.restore(formatted, masked.hidden, reindent=True, nested=True)


def _usable_around(text: str) -> bool:
    """A view that parses, or would once its fewest unreadable lines are hidden."""
    return conditional.parses(text) or isolate(text) is not None


def _source_rows(source: str, kept: list[str]) -> tuple[int, ...]:
    """The source lines (1-based) whose text was left as written in some view."""
    texts = {line.strip() for hidden in kept for line in hidden.splitlines() if line.strip()}
    return tuple(number for number, line in enumerate(source.splitlines(), start=1) if line.strip() in texts)


def _format_around(source: str, settings: Settings, lang_version: float) -> FormatResult | None:
    """Format all but the fewest lines that keep the source from parsing."""
    masked = isolate(source)
    if masked is None:
        return None
    formatted = _format_parsed(masked.text, settings, lang_version)
    if _placements(masked.text) != _placements(formatted):
        raise FormattingError("a line the parser cannot read would move")
    text = conditional.restore(formatted, masked.hidden, reindent=True)
    return FormatResult(text, masked.hidden_rows)


def _placements(text: str) -> list[tuple[str, str, str]]:
    """Each hidden line's placeholder with the code tokens just before and after it."""
    out: list[tuple[str, str, str]] = []
    previous = ""
    pending: list[str] = []
    stack = [parse(text).root_node]
    leaves = []
    while stack:
        node = stack.pop()
        if node.child_count == 0 or node.type == "comment":
            leaves.append(node)
        else:
            stack.extend(reversed(node.children))
    for leaf in leaves:
        content = (leaf.text or b"").decode("utf-8")
        if leaf.type == "comment":
            if conditional.is_placeholder(content):
                pending.append(content)
            continue
        for placeholder in pending:
            out.append((placeholder, previous, content))
        pending = []
        previous = content
    out.extend((placeholder, previous, "") for placeholder in pending)
    return out


def _same_view(before: str, after: str, *, around: bool = False) -> bool:
    """Whether two views of a file, with the same branches hidden, are the same code.

    With ``around``, views that hold unreadable lines are compared with those
    lines hidden in both, and the hidden lines must match apart from indentation.
    """
    try:
        old, new = build(before), build(after)
    except CSharpSyntaxError:
        if not around:
            return False
        first = isolate(before)
        if first is None:
            return False
        # The same lines, found by their text, are hidden in the formatted view.
        second = _hide_matching(after, _stripped(first.hidden.values()))
        if second is None:
            return False
        try:
            old, new = build(first.text), build(second.text)
        except CSharpSyntaxError:
            return False
    if canonical(old.root) != canonical(new.root):
        return False
    # Hidden text differs between the views by design: it was formatted in its own view.
    return _visible_words(old) == _visible_words(new)


def _visible_words(file: SourceFile) -> object:
    words = comment_words(file)
    return {word: count for word, count in words.items() if not word.startswith("#prettycsharp-hidden") and not _is_id(word)}


def _is_id(word: str) -> bool:
    return len(word) == 16 and all(c in "0123456789abcdef" for c in word)


def _format_parsed(source: str, settings: Settings, lang_version: float) -> str:
    file = build(source)
    expected_tree = canonical(file.root)
    expected_comments = comment_words(file)
    rewrite(file, settings, lang_version)
    text = print_file(file, settings, lang_version)
    try:
        result = build(text)
    except CSharpSyntaxError as error:
        raise FormattingError(f"the formatted code does not parse ({error})") from None
    if canonical(result.root) != expected_tree or comment_words(result) != expected_comments:
        try:
            from prettycsharp.verify import verify

            original = build(source)
            verify(original, result)
        except VerificationError as error:
            raise FormattingError(str(error)) from None
        raise FormattingError("the formatted code differs from the source")
    return text


def _run_with_big_stack(work: Callable[[], T]) -> T:
    result: list[T] = []
    failure: list[BaseException] = []

    def target() -> None:
        try:
            result.append(work())
        except RecursionError:
            failure.append(FormattingError("the file is nested too deeply to format"))
        except BaseException as error:  # noqa: BLE001 - re-raised in the caller's thread
            failure.append(error)

    with _lock:
        old_limit = sys.getrecursionlimit()
        old_size = threading.stack_size()
        try:
            threading.stack_size(_STACK_SIZE)
            sys.setrecursionlimit(max(old_limit, _RECURSION_LIMIT))
            worker = threading.Thread(target=target, name="prettycsharp-format")
            worker.start()
            worker.join()
        finally:
            threading.stack_size(old_size)
            sys.setrecursionlimit(old_limit)
    if failure:
        raise failure[0]
    return result[0]


def _stripped(texts: Iterable[str]) -> list[str]:
    return [line.strip() for text in texts for line in text.splitlines()]


def _hide_matching(text: str, wanted: list[str]) -> conditional.Masked | None:
    """Hide the lines of ``text`` whose stripped text is ``wanted``, in order; None if any is missing."""
    lines = conditional._split_lines(text)
    keep = [True] * len(lines)
    position = 0
    for number, line in enumerate(lines):
        if position < len(wanted) and line.strip() == wanted[position]:
            keep[number] = False
            position += 1
    if position != len(wanted):
        return None
    return conditional.hide(lines, keep, salt="isolate:")
