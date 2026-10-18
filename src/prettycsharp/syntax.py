"""The syntax model the formatter works on.

tree-sitter's tree is copied into ``Node`` objects that can be rearranged by
the rewrites. Comments are taken out of the tree and attached to tokens as
trivia: a comment on the same line after a token trails it, and any other
comment leads the next token. Every token also records how many line breaks
came before it, which is how blank lines are preserved.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from tree_sitter import Node as TSNode
from tree_sitter import Tree

from prettycsharp.parsing import parse

# Node types whose text is printed exactly as written. Interpolated strings
# carry code and text in one token stream whose whitespace is content.
ATOMIC_TYPES = frozenset(
    {
        "interpolated_string_expression",
        "string_literal",
        "verbatim_string_literal",
        "raw_string_literal",
        "character_literal",
        "preproc_arg",
    }
)

DIRECTIVE_TYPES = frozenset(
    {
        "preproc_if",
        "preproc_elif",
        "preproc_else",
        "preproc_region",
        "preproc_endregion",
        "preproc_define",
        "preproc_undef",
        "preproc_pragma",
        "preproc_nullable",
        "preproc_error",
        "preproc_warning",
        "preproc_line",
        "preproc_if_in_attribute_list",
        "shebang_directive",
    }
)

# Containers whose children are a list of statements or members, where a
# preprocessor directive can stand between items.
LIST_TYPES = frozenset(
    {
        "compilation_unit",
        "declaration_list",
        "block",
        "switch_section",
        "switch_body",
        "file_scoped_namespace_declaration",
        "enum_member_declaration_list",
        "preproc_if",
        "preproc_elif",
        "preproc_else",
    }
)


@dataclass(eq=False, slots=True)
class Comment:
    text: str
    start: int
    end: int
    # Line breaks between the previous token or comment and this comment.
    newlines_before: int = 0
    # Whether only whitespace precedes the comment on its line.
    own_line: bool = False
    # Whether a line break follows the comment before the next token.
    newline_after: bool = False

    @property
    def is_line(self) -> bool:
        return self.text.startswith("//")

    @property
    def is_doc(self) -> bool:
        return self.text.startswith("///") and not self.text.startswith("////")


@dataclass(eq=False, slots=True)
class Node:
    type: str
    named: bool = True
    children: list[Node] = dataclass_field(default_factory=list)
    field: str | None = None
    start: int = -1
    end: int = -1
    # Leaves only: the token's exact text.
    text: str | None = None
    parent: Node | None = None
    leading: list[Comment] = dataclass_field(default_factory=list)
    trailing: list[Comment] = dataclass_field(default_factory=list)
    newlines_before: int = 0
    # Line, column of the start in the original source; -1 when synthesized.
    line: int = -1
    column: int = -1
    end_line: int = -1
    # Printed exactly as written: set for atomic nodes, ignored regions and
    # statements holding a preprocessor directive the printer cannot place.
    verbatim: bool = False

    @property
    def is_token(self) -> bool:
        return self.text is not None

    def child(self, field_name: str) -> Node | None:
        for c in self.children:
            if c.field == field_name:
                return c
        return None

    def children_of(self, field_name: str) -> list[Node]:
        return [c for c in self.children if c.field == field_name]

    def first_of(self, *types: str) -> Node | None:
        for c in self.children:
            if c.type in types:
                return c
        return None

    def named_children(self) -> list[Node]:
        return [c for c in self.children if c.named]

    def tokens(self) -> Iterator[Node]:
        stack = [self]
        while stack:
            node = stack.pop()
            if node.text is not None:
                yield node
            else:
                stack.extend(reversed(node.children))

    def first_token(self) -> Node | None:
        node = self
        while node.text is None:
            if not node.children:
                return None
            node = node.children[0]
        return node

    def last_token(self) -> Node | None:
        node = self
        while node.text is None:
            if not node.children:
                return None
            node = node.children[-1]
        return node

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.text is not None:
            return f"Token({self.type!r}, {self.text!r})"
        return f"Node({self.type!r}, {len(self.children)} children)"


def token(text: str, type: str | None = None) -> Node:
    """A synthesized token, such as a brace a rewrite adds."""
    return Node(type=type or text, named=False, text=text)


@dataclass(slots=True)
class SourceFile:
    source: bytes
    root: Node
    tokens: list[Node]
    # Comments left after the last token, attached to no token.
    trailing_comments: list[Comment]
    eol: str

    def text(self, start: int, end: int) -> str:
        return self.source[start:end].decode("utf-8")

    def slice(self, node: Node) -> str:
        return self.text(node.start, node.end)


def detect_eol(text: str) -> str:
    index = text.find("\n")
    if index > 0 and text[index - 1] == "\r":
        return "\r\n"
    if index >= 0:
        return "\n"
    if "\r" in text:
        return "\r"
    return "\n"


def build(source: str) -> SourceFile:
    """Parse ``source`` and build the syntax model, or raise CSharpSyntaxError."""
    tree = parse(source)
    data = source.encode("utf-8")
    root, tokens, comments = _copy(tree, data)
    trailing = _attach(data, tokens, comments)
    _mark_verbatim(root, data, tokens)
    return SourceFile(data, root, tokens, trailing, detect_eol(source))


def _copy(tree: Tree, data: bytes) -> tuple[Node, list[Node], list[Comment]]:
    tokens: list[Node] = []
    comments: list[Comment] = []
    root = _new_node(tree.root_node, None, data)
    # (tree-sitter node, our node) pairs whose children are still to copy.
    stack: list[tuple[TSNode, Node]] = [(tree.root_node, root)]
    while stack:
        ts_node, node = stack.pop()
        if node.text is not None:
            continue
        pending: list[tuple[TSNode, Node]] = []
        for i, ts_child in enumerate(ts_node.children):
            if ts_child.type == "comment":
                comments.append(_comment(ts_child, data))
                continue
            child = _new_node(ts_child, ts_node.field_name_for_child(i), data)
            child.parent = node
            node.children.append(child)
            pending.append((ts_child, child))
        stack.extend(reversed(pending))
    _restore_conditional_assignments(root)
    tokens.extend(root.tokens())
    comments.sort(key=lambda c: c.start)
    return root, tokens, comments


def _restore_conditional_assignments(root: Node) -> None:
    """Restore conditional accesses parsed with same-width ``!`` stand-ins."""
    nodes: list[Node] = []
    stack = [root]
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(node.children)
    for node in reversed(nodes):
        if node.type not in ("member_access_expression", "element_access_expression") or not node.children:
            continue
        receiver = node.children[0]
        if receiver.type != "postfix_unary_expression" or len(receiver.children) != 2:
            continue
        condition, question = receiver.children
        if question.type != "!" or question.text != "?":
            continue
        children = node.children[1:]
        if node.type == "element_access_expression":
            if len(children) != 1 or children[0].type != "bracketed_argument_list":
                continue
            children = children[0].children
        binding = Node(
            type="member_binding_expression" if node.type == "member_access_expression" else "element_binding_expression",
            named=True,
            start=children[0].start,
            end=node.end,
            line=children[0].line,
            column=children[0].column,
            end_line=node.end_line,
            children=children,
            parent=node,
        )
        for child in children:
            child.parent = binding
        condition.field = "condition"
        condition.parent = node
        question.type = "?"
        question.parent = node
        node.type = "conditional_access_expression"
        node.children = [condition, question, binding]


def _new_node(ts_node: TSNode, field_name: str | None, data: bytes) -> Node:
    text = None
    end = ts_node.end_byte
    if ts_node.child_count == 0 or ts_node.type in ATOMIC_TYPES:
        text = data[ts_node.start_byte : end].decode("utf-8")
        if ts_node.type == "preproc_arg":
            # A directive's argument runs to the line break, and on a CRLF
            # line it takes the \r with it.
            text = text.rstrip()
            end = ts_node.start_byte + len(text.encode("utf-8"))
    return Node(
        type=ts_node.type,
        named=ts_node.is_named,
        field=field_name,
        start=ts_node.start_byte,
        end=end,
        text=text,
        line=ts_node.start_point[0],
        column=ts_node.start_point[1],
        end_line=ts_node.end_point[0],
    )


def _comment(ts_node: TSNode, data: bytes) -> Comment:
    text = data[ts_node.start_byte : ts_node.end_byte].decode("utf-8")
    if text.startswith("//"):
        text = text.rstrip("\r\n")
    return Comment(text=text, start=ts_node.start_byte, end=ts_node.start_byte + len(text.encode("utf-8")))


def _attach(data: bytes, tokens: list[Node], comments: list[Comment]) -> list[Comment]:
    """Attach each comment to a token; return those after the last token."""
    trailing_file: list[Comment] = []
    ti = 0
    previous_end = 0
    previous_token: Node | None = None
    ci = 0
    # Walk tokens and comments together in source order.
    while ti < len(tokens) or ci < len(comments):
        next_is_comment = ci < len(comments) and (ti >= len(tokens) or comments[ci].start < tokens[ti].start)
        if next_is_comment:
            comment = comments[ci]
            ci += 1
            gap = data[previous_end : comment.start]
            comment.newlines_before = _count_newlines(gap)
            comment.own_line = comment.newlines_before > 0 or previous_end == 0
            following_end = tokens[ti].start if ti < len(tokens) else len(data)
            following = comments[ci].start if ci < len(comments) else following_end
            comment.newline_after = _count_newlines(data[comment.end : min(following, following_end)]) > 0
            if previous_token is not None and comment.newlines_before == 0 and not _has_leading_pending(previous_token):
                previous_token.trailing.append(comment)
            elif ti < len(tokens):
                tokens[ti].leading.append(comment)
            else:
                trailing_file.append(comment)
            previous_end = comment.end
        else:
            tok = tokens[ti]
            ti += 1
            tok.newlines_before = _count_newlines(data[previous_end : tok.start])
            previous_end = tok.end
            previous_token = tok
    return trailing_file


def _has_leading_pending(token: Node) -> bool:
    # A comment trails a token only if no line break separates them; once a
    # comment on that line was attached as leading to a later token, stop.
    return False


def _count_newlines(gap: bytes) -> int:
    # \r\n counts once; a lone \r counts as a line break too.
    return gap.count(b"\n") + gap.count(b"\r") - gap.count(b"\r\n")


def _mark_verbatim(root: Node, data: bytes, tokens: list[Node]) -> None:
    # A node whose tokens leave non-whitespace text uncovered between them
    # (tree-sitter keeps some text in no leaf) is printed as written.
    for left, right in zip(tokens, tokens[1:], strict=False):
        gap = data[left.end : right.start]
        if gap.strip() and not _gap_is_comments(gap, left, right):
            ancestor = _common_ancestor(left, right)
            if ancestor is not None:
                ancestor.verbatim = True
    # Directive lines print as written, so no rewrite may touch them: a
    # simple directive, and the condition of #if and #elif.
    for node in _walk(root):
        if node.type in ("preproc_if", "preproc_elif"):
            condition = node.child("condition")
            if condition is not None:
                condition.verbatim = True
        elif node.type in DIRECTIVE_TYPES and node.type != "preproc_else":
            node.verbatim = True
    # A preprocessor directive outside a list makes its list item verbatim.
    for node in _walk(root):
        if node.type in DIRECTIVE_TYPES and node.parent is not None and node.parent.type not in LIST_TYPES:
            item = node.parent
            while item.parent is not None and item.parent.type not in LIST_TYPES:
                item = item.parent
            item.verbatim = True


def _gap_is_comments(gap: bytes, left: Node, right: Node) -> bool:
    text = gap.decode("utf-8")
    for comment in left.trailing + right.leading:
        text = text.replace(comment.text, "", 1)
    return not text.strip()


def _common_ancestor(a: Node, b: Node) -> Node | None:
    ancestors = set()
    node: Node | None = a
    while node is not None:
        ancestors.add(id(node))
        node = node.parent
    node = b
    while node is not None:
        if id(node) in ancestors:
            return node
        node = node.parent
    return None


def _walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def walk(root: Node) -> Iterator[Node]:
    return _walk(root)
