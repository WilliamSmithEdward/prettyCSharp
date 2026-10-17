"""Formatting code that conditional compilation splits.

tree-sitter reads every ``#if`` branch as code. When the branches together
are not valid C#, as in ``#if X`` / ``class A : I`` / ``#else`` /
``class A`` / ``#endif`` / ``{ ... }``, the file does not parse. The compiler
sees one branch at a time, and so does this module: for a set of defined
symbols, every directive line and every line of an inactive branch is
replaced by a placeholder comment, which leaves complete C# to format. The
placeholders then go back to the text they stood for, exactly as written.

Doing that for symbol sets that between them make every branch active
formats every branch. Afterwards the result is checked under each symbol
set: with the same lines hidden, it must be the same code as the source.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from prettycsharp.parsing import CSharpSyntaxError, parse

_DIRECTIVE = re.compile(r"^[ \t]*#[ \t]*(if|elif|else|endif|define|undef)\b(.*)$")
_PLACEHOLDER = re.compile(r"^[ \t]*//#prettycsharp-hidden ([0-9a-f]{16})[ \t]*$")
_LINE_BREAK = re.compile(r"\r\n|\r|\n")
# At most this many symbol sets are formatted for one file.
MAX_PASSES = 16


class ConditionalError(ValueError):
    """The directives are unbalanced or a condition cannot be read."""


class BranchChanged(ConditionalError):
    """Seen through one of the symbol sets, the formatted file is different code."""


def has_conditionals(source: str) -> bool:
    for line in source.splitlines():
        found = _directive(line)
        if found is not None and found[0] == "if":
            return True
    return False


def _directive(line: str) -> tuple[str, str] | None:
    match = _DIRECTIVE.match(line)
    if match is None:
        return None
    rest = match.group(2)
    comment = rest.find("//")
    if comment >= 0:
        rest = rest[:comment]
    return match.group(1), rest.strip()


# Conditions ----------------------------------------------------------------


_TOKEN = re.compile(r"\s*(\|\||&&|==|!=|!|\(|\)|[A-Za-z_][A-Za-z0-9_]*)")


def symbols_in(condition: str) -> set[str]:
    return {t for t in _tokens(condition) if t[0].isalpha() or t[0] == "_"} - {"true", "false"}


def _tokens(condition: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(condition):
        match = _TOKEN.match(condition, position)
        if match is None:
            if condition[position:].strip():
                raise ConditionalError(f"cannot read the condition {condition!r}")
            break
        tokens.append(match.group(1))
        position = match.end()
    return tokens


def evaluate(condition: str, defined: set[str]) -> bool:
    """A preprocessor condition: ``||``, ``&&``, ``==``, ``!=``, ``!``, parentheses."""
    tokens = _tokens(condition)
    position = 0

    def peek() -> str | None:
        return tokens[position] if position < len(tokens) else None

    def take() -> str:
        nonlocal position
        if position >= len(tokens):
            raise ConditionalError(f"the condition {condition!r} ends too soon")
        position += 1
        return tokens[position - 1]

    def primary() -> bool:
        token = take()
        if token == "!":
            return not primary()
        if token == "(":
            value = disjunction()
            if take() != ")":
                raise ConditionalError(f"unbalanced parentheses in {condition!r}")
            return value
        if token in ("true", "false"):
            return token == "true"
        if token[0].isalpha() or token[0] == "_":
            return token in defined
        raise ConditionalError(f"cannot read the condition {condition!r}")

    def equality() -> bool:
        value = primary()
        while peek() in ("==", "!="):
            operator = take()
            other = primary()
            value = (value == other) if operator == "==" else (value != other)
        return value

    def conjunction() -> bool:
        value = equality()
        while peek() == "&&":
            take()
            value = equality() and value
        return value

    def disjunction() -> bool:
        value = conjunction()
        while peek() == "||":
            take()
            value = conjunction() or value
        return value

    result = disjunction()
    if position != len(tokens):
        raise ConditionalError(f"cannot read the condition {condition!r}")
    return result


# Masking -------------------------------------------------------------------


@dataclass
class Masked:
    text: str
    # Placeholder id to the exact text it stands for.
    hidden: dict[str, str] = field(default_factory=dict)
    # The directive lines (by number) of the branches this symbol set makes active.
    active_branches: frozenset[int] = frozenset()
    # Whether restore moves hidden lines to their placeholder's indentation.
    reindent: bool = False
    # The source lines (1-based) that were hidden, when the hiding chose lines.
    hidden_rows: tuple[int, ...] = ()


def _split_lines(source: str) -> list[str]:
    """Lines with their own line breaks, so joining them gives the source back."""
    lines: list[str] = []
    start = 0
    for match in _LINE_BREAK.finditer(source):
        lines.append(source[start : match.end()])
        start = match.end()
    if start < len(source):
        lines.append(source[start:])
    return lines


def _content(line: str) -> str:
    return line.rstrip("\r\n")


def mask(source: str, defined: Iterable[str]) -> Masked:
    """Hide directive lines and inactive branches behind placeholder comments."""
    symbols = set(defined)
    lines = _split_lines(source)
    keep: list[bool] = []
    active_branches: set[int] = set()
    # Each entry: (enclosing branch active, a branch already taken).
    stack: list[list[bool]] = []
    active = True
    for number, line in enumerate(lines):
        found = _directive(_content(line))
        if found is None:
            keep.append(active)
            continue
        kind, argument = found
        keep.append(False)
        if kind == "if":
            taken = active and evaluate(argument, symbols)
            stack.append([active, taken])
            active = taken
        elif kind in ("elif", "else"):
            if not stack:
                raise ConditionalError(f"#{kind} without #if on line {number + 1}")
            parent, already = stack[-1]
            chosen = parent and not already and (kind == "else" or evaluate(argument, symbols))
            stack[-1][1] = already or chosen
            active = chosen
        elif kind == "endif":
            if not stack:
                raise ConditionalError(f"#endif without #if on line {number + 1}")
            active = stack.pop()[0]
            continue
        elif active:
            # #define and #undef count only where they are compiled.
            names = symbols_in(argument)
            if kind == "define":
                symbols |= names
            else:
                symbols -= names
            continue
        if active and kind in ("if", "elif", "else"):
            active_branches.add(number)
    if stack:
        raise ConditionalError("#if without #endif")
    masked = hide(lines, keep)
    masked.active_branches = frozenset(active_branches)
    return masked


def hide(lines: Sequence[str], keep: Sequence[bool], *, reindent: bool = False) -> Masked:
    """Replace each run of lines not kept by one placeholder comment line.

    ``lines`` keep their line breaks. With ``reindent``, ``restore`` moves the
    hidden lines to the indentation their placeholder was printed at.
    """
    out: list[str] = []
    hidden: dict[str, str] = {}
    run: list[str] = []

    def flush(line_break: str) -> None:
        if not run:
            return
        text = "".join(run)
        # The position makes two runs with the same text distinct.
        identifier = hashlib.sha256(f"{len(hidden)}:{text}".encode()).hexdigest()[:16]
        hidden[identifier] = text.rstrip("\r\n")
        out.append(f"//#prettycsharp-hidden {identifier}{line_break}")
        run.clear()

    for line, kept in zip(lines, keep, strict=True):
        if kept:
            flush(_line_break(run[-1]) if run else "\n")
            out.append(line)
        else:
            run.append(line)
    flush(_line_break(run[-1]) if run else "")
    return Masked("".join(out), hidden, reindent=reindent)


def _line_break(line: str) -> str:
    content = _content(line)
    return line[len(content) :] or "\n"


def restore(text: str, hidden: dict[str, str], *, reindent: bool = False) -> str:
    """Put back the text each placeholder line stands for.

    With ``reindent``, hidden lines move to the indentation their placeholder
    was printed at, unless they could hold a multi-line string, whose
    content must not change.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in _split_lines(text):
        content = _content(line)
        match = _PLACEHOLDER.match(content)
        if match is None:
            out.append(line)
            continue
        identifier = match.group(1)
        if identifier not in hidden or identifier in seen:
            raise ConditionalError("a hidden line was lost or repeated while formatting")
        seen.add(identifier)
        original = hidden[identifier]
        if reindent:
            original = _reindent(original, content[: len(content) - len(content.lstrip())])
        out.append(original + line[len(content) :])
    if seen != set(hidden):
        raise ConditionalError("a hidden line was lost while formatting")
    return "".join(out)


_MULTILINE_STRING = re.compile(r'"""|@"|\$@"|@\$"')


def _reindent(text: str, indentation: str) -> str:
    """Shift lines that share the first line's indentation to ``indentation``."""
    if _MULTILINE_STRING.search(text):
        return text
    lines = _split_lines(text)
    first = _content(lines[0])
    old = first[: len(first) - len(first.lstrip())]
    shifted = []
    for line in lines:
        if line.startswith(old) and _content(line).strip():
            shifted.append(indentation + line[len(old) :])
        else:
            shifted.append(line)
    return "".join(shifted)


# Symbol sets ---------------------------------------------------------------


def all_symbols(source: str) -> list[str]:
    names: set[str] = set()
    for line in source.splitlines():
        found = _directive(line)
        if found is not None and found[0] in ("if", "elif", "define", "undef"):
            names |= symbols_in(found[1])
    return sorted(names)


def candidate_sets(symbols: Sequence[str]) -> list[frozenset[str]]:
    """Symbol sets to try, simplest first: none, each alone, all, all but each."""
    full = frozenset(symbols)
    sets: list[frozenset[str]] = [frozenset()]
    sets.extend(frozenset([s]) for s in symbols)
    sets.append(full)
    sets.extend(full - {s} for s in symbols)
    unique: list[frozenset[str]] = []
    for candidate in sets:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def branches(source: str) -> set[int]:
    """The line numbers of every #if, #elif and #else that is not itself hidden code."""
    found: set[int] = set()
    for number, line in enumerate(_split_lines(source)):
        directive = _directive(_content(line))
        if directive is not None and directive[0] in ("if", "elif", "else"):
            found.add(number)
    return found


def covering_sets(source: str) -> list[frozenset[str]]:
    """Symbol sets whose masked text parses and that together reach every branch they can."""
    wanted = branches(source)
    chosen: list[frozenset[str]] = []
    covered: set[int] = set()
    for candidate in candidate_sets(all_symbols(source)):
        if len(chosen) >= MAX_PASSES:
            break
        masked = mask(source, candidate)
        new = masked.active_branches - covered
        if chosen and not new:
            continue
        try:
            parse(masked.text)
        except CSharpSyntaxError:
            continue
        chosen.append(candidate)
        covered |= masked.active_branches
        if covered >= wanted:
            break
    return chosen


def format_conditional(
    source: str, format_masked: Callable[[str], str], same_code: Callable[[str, str], bool]
) -> str | None:
    """Format each symbol set's view of the file in turn.

    Returns None when no symbol set gives text that parses. Raises
    ConditionalError when the result, seen through any of the symbol sets
    used, is not the same code as the source (``same_code`` compares two
    masked texts).
    """
    sets = covering_sets(source)
    if not sets:
        return None
    text = source
    for symbols in sets:
        masked = mask(text, symbols)
        text = restore(format_masked(masked.text), masked.hidden)
    for symbols in sets:
        if not same_code(mask(source, symbols).text, mask(text, symbols).text):
            raise BranchChanged("a branch of an #if would change in meaning")
    return text


def is_placeholder(comment_text: str) -> bool:
    return _PLACEHOLDER.match(comment_text) is not None
