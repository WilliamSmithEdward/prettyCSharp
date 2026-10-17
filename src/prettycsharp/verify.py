"""Checking that formatting changed layout, never meaning.

The input and the output are parsed and reduced to canonical syntax trees,
which must be equal. Canonicalization removes the differences the rewrites
are allowed to make, each in its simplest form: every parenthesized
expression is replaced by what it holds (the tree keeps the grouping), the
modifiers of a declaration and a run of using directives are sorted, an
attribute list is split into one list per attribute, a trailing comma is
dropped, a single-statement body is put in expression form, a namespace is
made file-scoped, an embedded statement gets braces, and regions are
dropped. Comments must hold the same words, counted as a multiset, since
rewrapping and reordering move them.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from prettycsharp.syntax import Comment, Node, SourceFile

Canon = tuple[object, ...]

_EMBEDDED = {
    "if_statement": ("consequence", "alternative"),
    "while_statement": ("body",),
    "for_statement": ("body",),
    "foreach_statement": ("body",),
    "do_statement": ("body",),
    "using_statement": ("body",),
    "lock_statement": ("body",),
    "fixed_statement": ("body",),
}

_BODY_OWNERS = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "operator_declaration",
        "conversion_operator_declaration",
        "local_function_statement",
        "accessor_declaration",
    }
)

_MODIFIER_OWNERS = frozenset(
    {
        "class_declaration",
        "struct_declaration",
        "interface_declaration",
        "record_declaration",
        "enum_declaration",
        "delegate_declaration",
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "operator_declaration",
        "conversion_operator_declaration",
        "property_declaration",
        "indexer_declaration",
        "event_declaration",
        "event_field_declaration",
        "field_declaration",
        "local_function_statement",
    }
)


class VerificationError(Exception):
    """The formatted text would not mean what the source meant."""


def verify(before: SourceFile, after: SourceFile) -> None:
    left = canonical(before.root)
    right = canonical(after.root)
    if left != right:
        raise VerificationError(f"the formatted code differs from the source ({_first_difference(left, right)})")
    if comment_words(before) != comment_words(after):
        missing = comment_words(before) - comment_words(after)
        extra = comment_words(after) - comment_words(before)
        detail = next(iter(missing or extra))
        raise VerificationError(f"the comments changed ({detail!r})")


def comment_words(file: SourceFile) -> Counter[str]:
    words: Counter[str] = Counter()
    for comment in _all_comments(file):
        text = comment.text
        if text.startswith("///") and not text.startswith("////"):
            words["///" + text[3:].strip()] += 1
        elif text.startswith("//"):
            words.update(text[2:].split())
        else:
            lines = [line.strip() for line in text.splitlines()]
            words["/*" + "\n".join(lines)] += 1
    return words


def _all_comments(file: SourceFile) -> list[Comment]:
    comments: list[Comment] = list(file.trailing_comments)
    for token in file.tokens:
        comments.extend(token.leading)
        comments.extend(token.trailing)
    return comments


def canonical(node: Node) -> Canon:
    if node.text is not None:
        text = node.text.strip() if node.type == "preproc_arg" else node.text
        return (node.type, text)
    if node.type == "parenthesized_expression":
        inner = [c for c in node.children if c.named]
        if len(inner) == 1 and node.children[0].text == "(" and node.children[-1].text == ")":
            return canonical(inner[0])
    children = list(node.children)
    if node.type == "compilation_unit":
        children = _file_scoped(children)
    if node.type in _BODY_OWNERS:
        children = _expression_body(children)
    if node.type in ("property_declaration", "indexer_declaration"):
        children = _property_arrow(children)
    out: list[object] = []
    i = 0
    while i < len(children):
        child = children[i]
        if child.type in ("preproc_region", "preproc_endregion"):
            i += 1
            continue
        if child.type == "attribute_list" or child.type == "global_attribute":
            out.extend(_split_attributes(child))
        elif child.type == "using_directive":
            run = []
            while i < len(children) and children[i].type == "using_directive":
                run.append(canonical(children[i]))
                i += 1
            out.extend(sorted(run, key=repr))
            continue
        elif child.type == "modifier" and node.type in _MODIFIER_OWNERS:
            run = []
            while i < len(children) and children[i].type == "modifier":
                run.append(canonical(children[i]))
                i += 1
            out.extend(sorted(run, key=repr))
            continue
        elif (
            child.text == ","
            and i == len(children) - 2
            and children[-1].text in ("}", "]")
            and node.type != "array_rank_specifier"
        ):
            pass
        elif node.type in _EMBEDDED and is_embedded(node, child) and _needs_braces(node, child):
            out.append(("block", (("{", "{"), canonical(child), ("}", "}"))))
        else:
            out.append(canonical(child))
        i += 1
    return (node.type, tuple(out))


def is_embedded(parent: Node, child: Node) -> bool:
    """Whether ``child`` is a statement embedded in ``parent``, such as an if's body."""
    fields = _EMBEDDED.get(parent.type)
    if fields is None:
        return False
    if child.field in fields:
        return True
    # lock and fixed statements keep their body as an unnamed last child.
    return (
        parent.type in ("lock_statement", "fixed_statement")
        and child is parent.children[-1]
        and child.named
        and child.type.endswith(("statement", "block"))
    )


def _needs_braces(parent: Node, child: Node) -> bool:
    if child.type == "block":
        return False
    if parent.type == "if_statement" and child.field == "alternative" and child.type == "if_statement":
        return False
    return True


def _split_attributes(node: Node) -> list[Canon]:
    """``[t: A, B]`` as ``[t: A]`` ``[t: B]``."""
    target: list[Canon] = []
    attributes: list[Node] = []
    for child in node.children:
        if child.type == "attribute":
            attributes.append(child)
        elif child.type == "attribute_target_specifier":
            target.append(canonical(child))
        elif child.text not in ("[", "]", ","):
            target.append(canonical(child))
    if not attributes:
        return [canonical(node)]
    return [("attribute_list", (("[", "["), *target, canonical(a), ("]", "]"))) for a in attributes]


def _expression_body(children: list[Node]) -> list[Node]:
    """A block body of one return, expression or throw statement, in arrow form."""
    for index, child in enumerate(children):
        if child.field != "body" or child.type != "block":
            continue
        statements = child.children[1:-1]
        if len(statements) != 1:
            return children
        statement = statements[0]
        expression = _arrow_expression(statement)
        if expression is None:
            return children
        arrow = Node(type="arrow_expression_clause", field="body")
        arrow.children = [Node(type="=>", named=False, text="=>"), expression]
        semicolon = Node(type=";", named=False, text=";")
        rest = [c for c in children[index + 1 :] if c.text != ";"]
        return [*children[:index], arrow, semicolon, *rest]
    return children


def _arrow_expression(statement: Node) -> Node | None:
    kids = statement.children
    if statement.type == "expression_statement" and len(kids) == 2 and kids[1].text == ";":
        return kids[0]
    # return x; and return this;, not return ref x;
    if statement.type == "return_statement" and len(kids) == 3 and kids[2].text == ";" and kids[1].text != "ref":
        return kids[1]
    if statement.type == "throw_statement" and len(kids) == 3 and kids[2].text == ";":
        thrown = Node(type="throw_expression")
        thrown.children = [kids[0], kids[1]]
        return thrown
    return None


def _property_arrow(children: list[Node]) -> list[Node]:
    """A property with only a plain getter, in arrow form."""
    for index, child in enumerate(children):
        if child.type != "accessor_list":
            continue
        accessors = [c for c in child.children if c.type == "accessor_declaration"]
        others = [c for c in child.children if c.type != "accessor_declaration" and c.text not in ("{", "}")]
        if len(accessors) != 1 or others or index != len(children) - 1:
            return children
        accessor = accessors[0]
        if [c.text for c in accessor.children if c.type != "block" and c.type != "arrow_expression_clause"] not in (
            ["get"],
            ["get", ";"],
        ):
            return children
        body = _expression_body(accessor.children)
        arrow = next((c for c in body if c.type == "arrow_expression_clause"), None)
        if arrow is None:
            return children
        semicolon = Node(type=";", named=False, text=";")
        return [*children[:index], arrow, semicolon]
    return children


def _file_scoped(children: list[Node]) -> list[Node]:
    """The one block namespace of a file, as a file-scoped namespace."""
    namespaces = [c for c in children if c.type == "namespace_declaration"]
    if len(namespaces) != 1 or any(c.type == "file_scoped_namespace_declaration" for c in children):
        return children
    namespace = namespaces[0]
    index = children.index(namespace)
    allowed = ("using_directive", "extern_alias_directive", "global_attribute")
    if any(c.type not in allowed and not c.type.startswith("preproc") for c in children[:index]):
        return children
    if any(not c.type.startswith("preproc") for c in children[index + 1 :]):
        return children
    body = namespace.child("body")
    if body is None or body.type != "declaration_list" or len(body.children) < 2:
        return children
    members = body.children[1:-1]
    if any(_contains_namespace(m) for m in members):
        return children
    head = [c for c in namespace.children if c is not body]
    if any(c.text == ";" for c in head):
        return children
    scoped = Node(type="file_scoped_namespace_declaration")
    scoped.children = [*head, Node(type=";", named=False, text=";")]
    return [*children[:index], scoped, *members, *children[index + 1 :]]


def _contains_namespace(node: Node) -> bool:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.type in ("namespace_declaration", "file_scoped_namespace_declaration"):
            return True
        stack.extend(current.children)
    return False


def _first_difference(left: object, right: object, path: Sequence[str] = ()) -> str:
    if isinstance(left, tuple) and isinstance(right, tuple):
        if len(left) == 2 and len(right) == 2 and isinstance(left[1], str) and isinstance(right[1], str):
            if left != right:
                return f"{'/'.join(path)}: {left[1]!r} became {right[1]!r}"
            return ""
        if len(left) == 2 and len(right) == 2 and left[0] == right[0]:
            a, b = left[1], right[1]
            if isinstance(a, tuple) and isinstance(b, tuple):
                for x, y in zip(a, b, strict=False):
                    found = _first_difference(x, y, (*path, str(left[0])))
                    if found:
                        return found
                if len(a) != len(b):
                    return f"{'/'.join((*path, str(left[0])))}: {len(a)} children became {len(b)}"
                return ""
        return f"{'/'.join(path)}: {left[0]} became {right[0]}"
    return "/".join(path)
