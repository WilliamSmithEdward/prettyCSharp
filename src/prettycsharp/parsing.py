"""Parsing C# source into a tree-sitter concrete syntax tree."""

from __future__ import annotations

import tree_sitter_c_sharp
from tree_sitter import Language, Node, Parser, Tree

_LANGUAGE = Language(tree_sitter_c_sharp.language())


class CSharpSyntaxError(ValueError):
    """The source does not parse as C#, so it is not formatted.

    ``line`` and ``column`` are 1-based and point at the first error the
    parser found.
    """

    def __init__(self, line: int, column: int) -> None:
        super().__init__(f"syntax error at line {line}, column {column}")
        self.line = line
        self.column = column


def parse(source: str) -> Tree:
    """Parse ``source`` and return its tree, or raise CSharpSyntaxError."""
    tree = Parser(_LANGUAGE).parse(source.encode("utf-8"))
    if tree.root_node.has_error:
        node = _first_error(tree.root_node)
        row, column = node.start_point if node is not None else (0, 0)
        raise CSharpSyntaxError(row + 1, column + 1)
    return tree


def _first_error(root: Node) -> Node | None:
    # An ERROR node often wraps a whole declaration, so follow the first
    # erroneous child down to the innermost error, which is where the
    # problem is. A loop, so deep nesting cannot exhaust the Python stack.
    found = None
    node = root
    while True:
        if node.is_error or node.is_missing:
            found = node
        child = next((c for c in node.children if c.is_error or c.is_missing or c.has_error), None)
        if child is None:
            return found
        node = child
