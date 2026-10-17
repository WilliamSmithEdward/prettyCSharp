"""The formatting pipeline: parse, rewrite, print, then verify.

``format_source`` refuses input that does not parse (``CSharpSyntaxError``)
and raises ``FormattingError`` rather than return output that the verifier
finds different in meaning from the input. Formatting runs in a worker
thread with a large stack, so a deeply nested file fails cleanly instead of
crashing the interpreter.
"""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from typing import TypeVar

from prettycsharp.parsing import CSharpSyntaxError
from prettycsharp.printer import print_file
from prettycsharp.rewrites import rewrite
from prettycsharp.settings import Settings
from prettycsharp.syntax import build
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


def format_source(source: str, settings: Settings | None = None, *, lang_version: float | None = None) -> str:
    """Return ``source`` formatted.

    Raises CSharpSyntaxError when the source does not parse, and
    FormattingError when the result fails the formatter's own check.
    ``lang_version`` is the project's C# version, used when the settings say
    ``auto``; without it the latest version is assumed.
    """
    chosen = settings or Settings()
    version = lang_version_of(chosen, lang_version)
    return _run_with_big_stack(lambda: _format(source, chosen, version))


def _format(source: str, settings: Settings, lang_version: float) -> str:
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
