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

    def __init__(self, line: int, column: int, hint: str = "") -> None:
        super().__init__(f"syntax error at line {line}, column {column}{hint}")
        self.line = line
        self.column = column


_CONDITIONAL_HINT = " (seen whole, and with its #if branches taken one view at a time)"


def parse_tree(source: str) -> Tree:
    """Parse ``source``, errors and all."""
    data = source.encode("utf-8")
    if not data.endswith((b"\n", b"\r")):
        # The grammar wants a line break after a directive, even at the end
        # of the file. The extra byte comes after every node's text.
        data += b"\n"
    parser = Parser(_LANGUAGE)
    tree = parser.parse(data)
    if not tree.root_node.has_error:
        return tree
    return _compatibility_tree(parser, data, tree)


def _compatibility_tree(parser: Parser, data: bytes, original: Tree) -> Tree:
    """Resolve two grammar gaps without discarding tokens or accepting errors.

    Stand-ins have identical byte lengths. The syntax model reads token text
    from the original source and restores conditional-access node shapes.
    Only actual lexer tokens are considered, never text in comments/strings.
    """
    leaves: list[Node] = []
    stack = [original.root_node]
    while stack:
        node = stack.pop()
        if node.children:
            stack.extend(reversed(node.children))
        elif not node.is_missing and node.type != "comment":
            leaves.append(node)
    modified = bytearray(data)
    questions: set[int] = set()
    assignment_starts = {
        "=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", ">>>=", "??=",
        ".", "[", "(", "++", "--", "?",
        "+", "-", "*", "/", "%", "&", "|", "^", "<", ">",
    }
    for node, following in zip(leaves, leaves[1:], strict=False):
        if node.type == "required" and following.type in assignment_starts:
            modified[node.start_byte:node.end_byte] = b"req_ired"
        elif (
            node.type == "?"
            and following.type in (".", "[")
            and node.parent is not None
            and node.parent.type not in ("nullable_type", "conditional_expression")
        ):
            modified[node.start_byte] = ord("!")
            questions.add(node.start_byte)
    if modified == data:
        return original
    candidate = parser.parse(bytes(modified))
    if candidate.root_node.has_error:
        return original
    # Only repair null-conditional access along an assignment's receiver
    # chain. In particular, do not turn conditional ++/-- into valid input.
    allowed: set[int] = set()
    stack = [candidate.root_node]
    while stack:
        node = stack.pop()
        if node.type == "!" and node.start_byte in questions and _assignment_receiver(node):
            allowed.add(node.start_byte)
        stack.extend(node.children)
    for position in questions - allowed:
        modified[position] = ord("?")
    if questions - allowed:
        candidate = parser.parse(bytes(modified))
    return original if candidate.root_node.has_error else candidate


def _assignment_receiver(operator: Node) -> bool:
    receiver = operator.parent
    if receiver is None or receiver.type != "postfix_unary_expression":
        return False
    while receiver.parent is not None:
        parent = receiver.parent
        if parent.type == "assignment_expression":
            return parent.child_by_field_name("left") == receiver
        field = "function" if parent.type == "invocation_expression" else "expression"
        if parent.type not in ("member_access_expression", "element_access_expression", "invocation_expression"):
            return False
        if parent.child_by_field_name(field) != receiver:
            return False
        receiver = parent
    return False


def parse(source: str) -> Tree:
    """Parse ``source`` and return its tree, or raise CSharpSyntaxError."""
    tree = parse_tree(source)
    if tree.root_node.has_error:
        node = _first_error(tree.root_node)
        row, column = node.start_point if node is not None else (0, 0)
        hint = _CONDITIONAL_HINT if "#if" in source else ""
        raise CSharpSyntaxError(row + 1, column + 1, hint)
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
