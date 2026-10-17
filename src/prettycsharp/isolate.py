"""Formatting around code the grammar cannot parse (``syntax_errors = format_around``).

tree-sitter's grammar lags behind the newest C#, and one line it cannot read
makes the whole file unparseable; its error recovery can also misread the
code around that line. Instead of formatting a misread tree, this module
looks for the fewest whole lines whose removal makes the file parse, trying
lines around each error in turn. Those lines are hidden behind placeholder
comments (``conditional.hide``), the rest is formatted and verified, and the
lines go back, moved to the indentation their placeholder was printed at.

A hidden line goes back between the same two tokens it stood between, so
the order of the code's tokens cannot change.
"""

from __future__ import annotations

from tree_sitter import Node as TSNode

from prettycsharp.conditional import Masked, _content, _directive, _split_lines, hide, is_placeholder
from prettycsharp.parsing import parse_tree

# Limits that keep the search quick on any file.
MAX_REGIONS = 8
MAX_PARSES = 1500
WINDOW = 2
MAX_WIDTH = 3


def isolate(source: str) -> Masked | None:
    """The source with the fewest lines hidden that let it parse, or None."""
    lines = _split_lines(source)
    keep = [True] * len(lines)
    protected = [_protected(line) for line in lines]
    parses = 0
    for _ in range(MAX_REGIONS + 1):
        count, size, span = _errors(_blanked(lines, keep))
        parses += 1
        if count == 0:
            if all(keep) or not _worth_it(lines, keep):
                return None
            masked = hide(lines, keep, reindent=True, salt="isolate:")
            masked.hidden_rows = tuple(number + 1 for number, kept in enumerate(keep) if not kept)
            return masked
        if span is None:
            return None
        best: tuple[int, int] | None = None
        best_rows: list[int] = []
        start_row = max(span[0] - WINDOW, 0)
        end_row = min(span[1] + WINDOW, len(lines) - 1)
        for width in range(1, MAX_WIDTH + 1):
            for first in range(end_row, start_row - 1, -1):
                rows = list(range(first, min(first + width, len(lines))))
                if any(not keep[r] or protected[r] or not _content(lines[r]).strip() for r in rows):
                    continue
                trial = list(keep)
                for r in rows:
                    trial[r] = False
                metric = _errors(_blanked(lines, trial))[:2]
                parses += 1
                if parses > MAX_PARSES:
                    return None
                if metric < (count, size) and (best is None or metric < best):
                    best, best_rows = metric, rows
            if best is not None:
                break
        if best is None:
            return None
        for r in best_rows:
            keep[r] = False
    return None


def _worth_it(lines: list[str], keep: list[bool]) -> bool:
    """Code is left to format, and no more than half the lines were hidden."""
    written = [kept for line, kept in zip(lines, keep, strict=True) if _content(line).strip()]
    if sum(1 for kept in written if not kept) * 2 > len(written):
        return False
    tree = parse_tree(_blanked(lines, keep))
    return any(child.type != "comment" for child in tree.root_node.children)


def _protected(line: str) -> bool:
    """Lines never hidden: #if, #elif, #else and #endif hold the branches
    together, and a placeholder already stands for hidden text."""
    content = _content(line)
    if is_placeholder(content):
        return True
    found = _directive(content)
    return found is not None and found[0] in ("if", "elif", "else", "endif")


def _blanked(lines: list[str], keep: list[bool]) -> str:
    """The source with hidden lines emptied, so line numbers stay the same."""
    return "".join(line if kept else line[len(_content(line)) :] for line, kept in zip(lines, keep, strict=True))


def _errors(text: str) -> tuple[int, int, tuple[int, int] | None]:
    """(error nodes, bytes inside them, rows of the first one) for a parse of ``text``."""
    tree = parse_tree(text)
    if not tree.root_node.has_error:
        return 0, 0, None
    count = 0
    size = 0
    first: TSNode | None = None
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            count += 1
            size += node.end_byte - node.start_byte
            if first is None or node.start_byte < first.start_byte:
                first = node
            continue
        if node.has_error:
            stack.extend(node.children)
    if first is None:
        return 1, 0, None
    return count, size, (first.start_point[0], first.end_point[0])
