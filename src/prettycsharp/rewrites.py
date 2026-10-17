"""Syntax rewrites: the changes that move or replace tokens.

Each rewrite edits the syntax model in place before printing. A token that
is removed hands its comments to a neighbour, so no comment is lost; the
verifier checks that every rewrite left the code meaning the same.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from prettycsharp.conditional import is_placeholder
from prettycsharp.settings import Settings
from prettycsharp.syntax import Comment, Node, SourceFile, token, walk
from prettycsharp.verify import is_embedded

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

# Declarations whose attribute lists go one attribute per list.
_ATTRIBUTE_OWNERS = _MODIFIER_OWNERS | {"accessor_declaration", "enum_member_declaration", "compilation_unit"}

_BODY_OWNERS = frozenset(
    {
        "method_declaration",
        "constructor_declaration",
        "destructor_declaration",
        "operator_declaration",
        "conversion_operator_declaration",
        "local_function_statement",
    }
)

_LIST_WITH_TRAILING_COMMA = frozenset(
    {
        "initializer_expression",
        "collection_expression",
        "enum_member_declaration_list",
        "anonymous_object_creation_expression",
        "switch_expression",
        "with_expression",
        "list_pattern",
        "property_pattern_clause",
    }
)

_LITERALS = frozenset(
    {
        "integer_literal",
        "real_literal",
        "string_literal",
        "verbatim_string_literal",
        "raw_string_literal",
        "character_literal",
        "boolean_literal",
        "null_literal",
    }
)


def rewrite(file: SourceFile, settings: Settings, lang_version: float) -> None:
    root = file.root
    if settings.namespace_style != "preserve":
        target = settings.namespace_style
        if target == "file_scoped_if_supported":
            target = "file_scoped" if lang_version >= 10 else "block"
        if target == "file_scoped":
            to_file_scoped(file)
        else:
            to_block_scoped(file)
    if settings.using_order != "preserve":
        sort_usings(root, settings.using_order)
    if settings.modifiers is not None:
        order_modifiers(root, settings.modifiers)
    if settings.attributes == "separate":
        separate_attributes(root)
    elif settings.attributes == "combine":
        combine_attributes(root)
    if settings.expression_bodies != "preserve":
        expression_bodies(root, settings.expression_bodies, lang_version)
    if settings.parentheses != "preserve":
        remove_parentheses(root, settings.parentheses)
    if settings.braces == "always":
        add_braces(root)
    if settings.trailing_commas == "remove":
        remove_trailing_commas(root)


# Trivia ------------------------------------------------------------------


def _frozen(node: Node) -> bool:
    current: Node | None = node
    while current is not None:
        if current.verbatim:
            return True
        current = current.parent
    return False


def _has_comments(nodes: Iterable[Node]) -> bool:
    return any(t.leading or t.trailing for n in nodes for t in n.tokens())


def _after_hidden(node: Node) -> bool:
    """Whether a hidden #if branch or directive line stands just before the node."""
    first = node.first_token()
    return first is not None and any(is_placeholder(c.text) for c in first.leading)


def _has_verbatim(node: Node) -> bool:
    """Whether any part of the node is printed as written, and so must not move."""
    return any(n.verbatim for n in walk(node))


def _set_children(node: Node, children: list[Node]) -> None:
    node.children = children
    for child in children:
        child.parent = node


def _as_leading(comments: Sequence[Comment]) -> list[Comment]:
    for comment in comments:
        comment.own_line = True
        comment.newline_after = True
        comment.newlines_before = max(comment.newlines_before, 1)
    return list(comments)


# Namespaces --------------------------------------------------------------


def to_file_scoped(file: SourceFile) -> None:
    root = file.root
    children = root.children
    namespaces = [c for c in children if c.type == "namespace_declaration"]
    if len(namespaces) != 1 or any(c.type == "file_scoped_namespace_declaration" for c in children):
        return
    namespace = namespaces[0]
    if _frozen(namespace):
        return
    index = children.index(namespace)
    allowed = ("using_directive", "extern_alias_directive", "global_attribute")
    if any(c.type not in allowed and not c.type.startswith("preproc") for c in children[:index]):
        return
    if children[index + 1 :]:
        return
    body = namespace.child("body")
    if body is None or body.type != "declaration_list" or len(body.children) < 2:
        return
    head = [c for c in namespace.children if c is not body]
    if head[-1:] and head[-1].text == ";":
        return
    members = body.children[1:-1]
    if any(n.type in ("namespace_declaration", "file_scoped_namespace_declaration") for m in members for n in walk(m)):
        return
    open_tok, close_tok = body.children[0], body.children[-1]
    semicolon = token(";")
    # Comments around the braces move: after { to the first member, before
    # and after } to the end of the file.
    moved = _as_leading([*open_tok.leading, *open_tok.trailing])
    first = members[0].first_token() if members else None
    if first is not None:
        first.leading[:0] = moved
    else:
        file.trailing_comments[:0] = moved
    file.trailing_comments[:0] = _as_leading([*close_tok.leading, *close_tok.trailing])
    scoped = Node(type="file_scoped_namespace_declaration")
    _set_children(scoped, [*head, semicolon])
    _set_children(root, [*children[:index], scoped, *members])


def to_block_scoped(file: SourceFile) -> None:
    root = file.root
    children = root.children
    scoped = next((c for c in children if c.type == "file_scoped_namespace_declaration"), None)
    if scoped is None or _frozen(scoped) or not scoped.children or scoped.children[-1].text != ";":
        return
    index = children.index(scoped)
    members = children[index + 1 :]
    semicolon = scoped.children[-1]
    open_tok = token("{")
    close_tok = token("}")
    open_tok.trailing = list(semicolon.trailing)
    open_tok.leading = list(semicolon.leading)
    close_tok.leading = _as_leading(file.trailing_comments)
    file.trailing_comments = []
    body = Node(type="declaration_list", field="body")
    _set_children(body, [open_tok, *members, close_tok])
    namespace = Node(type="namespace_declaration")
    _set_children(namespace, [*scoped.children[:-1], body])
    _set_children(root, [*children[:index], namespace])


# Usings ----------------------------------------------------------------


def using_key(node: Node, order: str) -> tuple[int, int, int, str]:
    texts = [t.text or "" for t in node.tokens()]
    is_global = 0 if texts[:1] == ["global"] else 1
    words = [w for w in texts if w not in ("global", "using", ";")]
    if words[:1] == ["static"]:
        kind, words = 1, words[1:]
    elif "=" in words:
        kind = 2
    else:
        kind = 0
    if words[:1] == ["unsafe"]:
        words = words[1:]
    name = "".join(words)
    system = 1
    if order in ("system_first", "system_first_grouped") and (name == "System" or name.startswith("System.")):
        system = 0
    return (is_global, kind, system, name)


def sort_usings(root: Node, order: str) -> None:
    for node in walk(root):
        if node.type not in ("compilation_unit", "declaration_list") or _frozen(node):
            continue
        children = node.children
        i = 0
        while i < len(children):
            if children[i].type != "using_directive":
                i += 1
                continue
            end = i + 1
            # A hidden #if branch or directive line (see conditional.py) is a
            # boundary: no using moves across it.
            while end < len(children) and children[end].type == "using_directive" and not _after_hidden(children[end]):
                end += 1
            run = children[i:end]
            ordered = sorted(run, key=lambda n: using_key(n, order))
            if ordered != run:
                _keep_header(run, ordered)
                children[i:end] = ordered
            i = end


def _keep_header(run: Sequence[Node], ordered: Sequence[Node]) -> None:
    """The comments above the first item stay above the first item."""
    old = run[0].first_token()
    new = ordered[0].first_token()
    if old is None or new is None or old is new:
        return
    header = old.leading
    old.leading = []
    new.leading[:0] = header
    old.newlines_before, new.newlines_before = new.newlines_before, old.newlines_before


# Modifiers ---------------------------------------------------------------


def modifier_rank(text: str, order: Sequence[str]) -> float:
    if text == "partial":
        return 1000
    if text == "ref":
        return 999
    if text == "const":
        text = "static"
    if text in order:
        return order.index(text)
    return 900


def order_modifiers(root: Node, order: Sequence[str]) -> None:
    for node in walk(root):
        if node.type not in _MODIFIER_OWNERS or _frozen(node):
            continue
        indexes = [i for i, c in enumerate(node.children) if c.type == "modifier"]
        if len(indexes) < 2 or indexes[-1] - indexes[0] != len(indexes) - 1:
            continue
        run = [node.children[i] for i in indexes]
        if any(_after_hidden(m) for m in run[1:]):
            continue
        ordered = sorted(run, key=lambda m: modifier_rank(_token_text(m), order))
        if ordered != run:
            _keep_header(run, ordered)
            node.children[indexes[0] : indexes[-1] + 1] = ordered


# Attributes --------------------------------------------------------------


def separate_attributes(root: Node) -> None:
    for node in list(walk(root)):
        if node.type not in _ATTRIBUTE_OWNERS or _frozen(node):
            continue
        children: list[Node] = []
        changed = False
        for child in node.children:
            if child.type in ("attribute_list", "global_attribute"):
                pieces = _split_list(child)
                changed = changed or len(pieces) > 1
                children.extend(pieces)
            else:
                children.append(child)
        if changed:
            _set_children(node, children)


def _split_list(node: Node) -> list[Node]:
    kids = node.children
    attributes = [c for c in kids if c.type == "attribute"]
    if len(attributes) < 2 or kids[0].text != "[" or kids[-1].text != "]":
        return [node]
    if any(c.type.startswith("preproc") for c in kids):
        return [node]
    target = [c for c in kids[1:-1] if c.type not in ("attribute",) and c.text != ","]
    commas = [c for c in kids if c.text == "," and not c.named]
    # A comma's comments go to the attribute before it.
    for comma, attribute in zip(commas, attributes, strict=False):
        last = attribute.last_token()
        if last is not None:
            last.trailing.extend(comma.trailing)
            last.trailing.extend(comma.leading)
    pieces: list[Node] = []
    for i, attribute in enumerate(attributes):
        open_tok = kids[0] if i == 0 else token("[")
        close_tok = kids[-1] if i == len(attributes) - 1 else token("]")
        piece_target = target if i == 0 else [_copy_tokens(t) for t in target]
        piece = Node(type=node.type, field=node.field)
        _set_children(piece, [open_tok, *piece_target, attribute, close_tok])
        pieces.append(piece)
    return pieces


def _copy_tokens(node: Node) -> Node:
    if node.text is not None:
        return Node(type=node.type, named=node.named, text=node.text, field=node.field)
    copy = Node(type=node.type, named=node.named, field=node.field)
    _set_children(copy, [_copy_tokens(c) for c in node.children])
    return copy


def combine_attributes(root: Node) -> None:
    for node in list(walk(root)):
        if node.type not in _ATTRIBUTE_OWNERS or _frozen(node):
            continue
        children: list[Node] = []
        for child in node.children:
            previous = children[-1] if children else None
            if (
                child.type == "attribute_list"
                and previous is not None
                and previous.type == "attribute_list"
                and _target_text(previous) == _target_text(child)
                and not _has_comments([child])
                and not any(c.type.startswith("preproc") for c in child.children + previous.children)
            ):
                attributes = [c for c in child.children if c.type == "attribute"]
                merged = previous.children[:-1]
                for attribute in attributes:
                    merged.extend([token(","), attribute])
                merged.append(previous.children[-1])
                _set_children(previous, merged)
            else:
                children.append(child)
        _set_children(node, children)


def _target_text(node: Node) -> str:
    target = node.first_of("attribute_target_specifier")
    return "".join(t.text or "" for t in target.tokens()) if target is not None else ""


# Expression bodies -------------------------------------------------------


def expression_bodies(root: Node, mode: str, lang_version: float) -> None:
    for node in list(walk(root)):
        if _frozen(node):
            continue
        if node.type in _BODY_OWNERS:
            if mode == "prefer":
                if node.type in ("constructor_declaration", "destructor_declaration") and lang_version < 7:
                    continue
                if lang_version >= 6:
                    _block_to_arrow(node)
            elif mode in ("block", "properties_only"):
                _arrow_to_block(node, _returns_value(node))
        elif node.type in ("property_declaration", "indexer_declaration", "event_declaration"):
            accessors = node.child("accessors")
            if mode in ("prefer", "properties_only"):
                if accessors is not None and lang_version >= 7:
                    for accessor in accessors.children:
                        if accessor.type == "accessor_declaration":
                            _block_to_arrow(accessor)
                if node.type != "event_declaration" and lang_version >= 6:
                    _getter_to_property_arrow(node)
            elif mode == "block":
                if node.type != "event_declaration":
                    _property_arrow_to_getter(node)
                accessors = node.child("accessors")
                if accessors is not None:
                    for accessor in accessors.children:
                        if accessor.type == "accessor_declaration":
                            keyword = accessor.child("name") or accessor.first_token()
                            returns = keyword is not None and keyword.text == "get"
                            _arrow_to_block(accessor, returns)


def _block_to_arrow(node: Node) -> None:
    body = node.child("body")
    if body is None or body.type != "block" or len(body.children) != 3:
        return
    statement = body.children[1]
    if _has_comments([body.children[0], body.children[2]]) or _has_comments([statement]) or _has_verbatim(statement):
        return
    expression = _statement_expression(statement)
    if expression is None:
        return
    arrow = Node(type="arrow_expression_clause", field="body")
    _set_children(arrow, [token("=>"), expression])
    semicolon = statement.children[-1]
    index = node.children.index(body)
    _set_children(node, [*node.children[:index], arrow, semicolon, *node.children[index + 1 :]])


def _statement_expression(statement: Node) -> Node | None:
    kids = statement.children
    if not kids or kids[-1].text != ";":
        return None
    if statement.type == "expression_statement" and len(kids) == 2:
        return kids[0]
    if statement.type == "return_statement" and len(kids) == 3 and kids[1].text != "ref":
        return kids[1]
    if statement.type == "throw_statement" and len(kids) == 3 and kids[1].named:
        thrown = Node(type="throw_expression")
        _set_children(thrown, [kids[0], kids[1]])
        return thrown
    return None


def _returns_value(node: Node) -> bool:
    """Whether a block body for this member needs ``return``."""
    if node.type in ("constructor_declaration", "destructor_declaration"):
        return False
    if node.type in ("operator_declaration", "conversion_operator_declaration"):
        return True
    returns = node.child("returns") or node.child("type")
    if returns is None:
        return False
    text = "".join(t.text or "" for t in returns.tokens())
    if text == "void":
        return False
    is_async = any(c.type == "modifier" and c.first_token() and c.first_token().text == "async" for c in node.children)  # type: ignore[union-attr]
    if is_async and text in ("Task", "ValueTask", "System.Threading.Tasks.Task", "System.Threading.Tasks.ValueTask"):
        return False
    return True


def _arrow_to_block(node: Node, returns: bool) -> None:
    arrow = next((c for c in node.children if c.type == "arrow_expression_clause"), None)
    if arrow is None or len(arrow.children) != 2:
        return
    index = node.children.index(arrow)
    after = node.children[index + 1 :]
    if not after or after[0].text != ";":
        return
    semicolon = after[0]
    arrow_tok, expression = arrow.children
    if arrow_tok.leading or arrow_tok.trailing:
        return
    if expression.type == "throw_expression" and len(expression.children) == 2:
        statement = Node(type="throw_statement")
        _set_children(statement, [expression.children[0], expression.children[1], semicolon])
    elif returns:
        statement = Node(type="return_statement")
        _set_children(statement, [token("return"), expression, semicolon])
    else:
        statement = Node(type="expression_statement")
        _set_children(statement, [expression, semicolon])
    body = Node(type="block", field="body")
    _set_children(body, [token("{"), statement, token("}")])
    _set_children(node, [*node.children[:index], body, *after[1:]])


def _getter_to_property_arrow(node: Node) -> None:
    accessors = node.child("accessors")
    if accessors is None or node.children[-1] is not accessors or _frozen(accessors) or _has_verbatim(accessors):
        return
    inner = accessors.children[1:-1]
    if len(inner) != 1 or inner[0].type != "accessor_declaration":
        return
    accessor = inner[0]
    if [c.text for c in accessor.children[:1]] != ["get"]:
        return
    arrow = accessor.first_of("arrow_expression_clause")
    if arrow is None or len(accessor.children) != 3 or accessor.children[2].text != ";":
        return
    if _has_comments([accessors.children[0], accessors.children[-1], accessor.children[0]]):
        return
    arrow.field = "value"
    _set_children(node, [*node.children[:-1], arrow, accessor.children[2]])


def _property_arrow_to_getter(node: Node) -> None:
    arrow = node.child("value")
    if arrow is None or arrow.type != "arrow_expression_clause" or len(arrow.children) != 2:
        return
    index = node.children.index(arrow)
    after = node.children[index + 1 :]
    if [c.text for c in after] != [";"]:
        return
    accessor = Node(type="accessor_declaration")
    get = token("get")
    get.field = "name"
    block_arrow = Node(type="arrow_expression_clause", field="body")
    _set_children(block_arrow, arrow.children)
    _set_children(accessor, [get, block_arrow, after[0]])
    _arrow_to_block(accessor, True)
    accessors = Node(type="accessor_list", field="accessors")
    _set_children(accessors, [token("{"), accessor, token("}")])
    _set_children(node, [*node.children[:index], accessors])


# Parentheses -------------------------------------------------------------


def remove_parentheses(root: Node, mode: str) -> None:
    for node in list(walk(root)):
        if node.type != "parenthesized_expression" or _frozen(node) or node.parent is None:
            continue
        kids = node.children
        if len(kids) != 3 or kids[0].text != "(" or kids[2].text != ")":
            continue
        if kids[0].leading or kids[0].trailing or kids[2].leading or kids[2].trailing:
            continue
        inner = kids[1]
        if mode == "remove_obvious" and not _obviously_redundant(node, inner):
            continue
        if mode == "remove_redundant" and not (_obviously_redundant(node, inner) or _precedence_redundant(node, inner)):
            continue
        if _next_token_text(node) == "<" and inner.type == "identifier":
            continue
        parent = node.parent
        inner.field = node.field
        index = parent.children.index(node)
        parent.children[index] = inner
        inner.parent = parent


def _obviously_redundant(node: Node, inner: Node) -> bool:
    parent = node.parent
    assert parent is not None
    if node.field == "condition" and parent.type in ("if_statement", "while_statement", "do_statement"):
        return True
    if parent.type in ("return_statement", "throw_statement", "yield_statement"):
        return parent.children[-1].text == ";" and parent.children[-2] is node
    if inner.type == "identifier":
        return True
    if inner.type in _LITERALS:
        numeric = inner.type in ("integer_literal", "real_literal")
        return not (numeric and parent.type in ("member_access_expression", "element_access_expression", "invocation_expression", "conditional_access_expression", "postfix_unary_expression"))
    if inner.type == "parenthesized_expression":
        return True
    return False


_PRIMARY = frozenset(
    {
        "identifier",
        "member_access_expression",
        "invocation_expression",
        "element_access_expression",
        "object_creation_expression",
        "typeof_expression",
        "default_expression",
        "sizeof_expression",
        "checked_expression",
        "generic_name",
        "this_expression",
        "parenthesized_expression",
        "interpolated_string_expression",
    }
)

_PRECEDENCE = {
    "??": 2,
    "||": 3,
    "&&": 4,
    "|": 5,
    "^": 6,
    "&": 7,
    "==": 8,
    "!=": 8,
    "<": 9,
    ">": 9,
    "<=": 9,
    ">=": 9,
    "<<": 10,
    ">>": 10,
    ">>>": 10,
    "+": 11,
    "-": 11,
    "*": 12,
    "/": 12,
    "%": 12,
}

# Contexts where any expression may stand without parentheses.
_OPEN_CONTEXTS = frozenset(
    {
        "argument",
        "arrow_expression_clause",
        "variable_declarator",
        "expression_statement",
        "initializer_expression",
        "return_statement",
        "throw_statement",
        "yield_statement",
        "interpolation",
        "attribute_argument",
    }
)


def _precedence_redundant(node: Node, inner: Node) -> bool:
    parent = node.parent
    assert parent is not None
    # Next to a type test or a pattern, the grammar can read the operators
    # differently without the parentheses: x is T || (y is A or B).
    neighbours = [inner, *(c for c in parent.children if c is not node)] if parent.type == "binary_expression" else [inner]
    if any(_has_type_test(n) for n in neighbours) or _misparsed_access(inner):
        return False
    if parent.type in _OPEN_CONTEXTS:
        return inner.type not in ("assignment_expression",) or parent.type == "expression_statement"
    if parent.type == "assignment_expression" and node.field == "right":
        return True
    if inner.type in _PRIMARY and parent.type not in ("cast_expression",):
        return inner.type not in ("integer_literal", "real_literal")
    if parent.type == "binary_expression" and inner.type == "binary_expression":
        outer_op = parent.child("operator")
        inner_op = inner.child("operator")
        if outer_op is None or inner_op is None:
            return False
        outer = _PRECEDENCE.get(outer_op.text or "")
        own = _PRECEDENCE.get(inner_op.text or "")
        if outer is None or own is None:
            return False
        if own > outer:
            return True
        if own == outer and node.field == "left" and outer_op.text != "??":
            return True
    return False


def _misparsed_access(node: Node) -> bool:
    """A binary expression as the target of an access or call, which only a
    misparse makes: the grammar reads a?[i] ?? b?.M() as (a?[i] ?? b)?.M()."""
    for n in walk(node):
        if n.type in ("conditional_access_expression", "member_access_expression", "invocation_expression"):
            target = n.child("condition") or n.child("expression") or n.child("function")
            if target is not None and target.type == "binary_expression":
                return True
    return False


def _has_type_test(node: Node) -> bool:
    return any(
        n.type in ("is_pattern_expression", "is_expression", "as_expression") or n.type.endswith("_pattern")
        for n in walk(node)
    )


def _next_token_text(node: Node) -> str | None:
    last = node.last_token()
    current: Node | None = node
    while current is not None and current.parent is not None:
        siblings = current.parent.children
        index = siblings.index(current)
        if index + 1 < len(siblings):
            following = siblings[index + 1].first_token()
            return following.text if following is not None else None
        current = current.parent
    del last
    return None


# Braces ----------------------------------------------------------------


def add_braces(root: Node) -> None:
    for node in list(walk(root)):
        if _frozen(node):
            continue
        for index, child in enumerate(node.children):
            if not is_embedded(node, child) or child.type == "block":
                continue
            if node.type == "if_statement" and child.field == "alternative" and child.type == "if_statement":
                continue
            if child.type in ("using_statement", "fixed_statement") and child.type == node.type:
                continue
            block = Node(type="block", field=child.field)
            child.field = None
            _set_children(block, [token("{"), child, token("}")])
            node.children[index] = block
            block.parent = node


# Trailing commas -----------------------------------------------------------


def remove_trailing_commas(root: Node) -> None:
    for node in walk(root):
        if node.type not in _LIST_WITH_TRAILING_COMMA or _frozen(node) or len(node.children) < 3:
            continue
        comma = node.children[-2]
        close = node.children[-1]
        if comma.text != "," or comma.named or close.text not in ("}", "]"):
            continue
        before = node.children[-3].last_token()
        if before is None:
            continue
        before.trailing.extend(comma.trailing)
        close.leading[:0] = _as_leading(comma.leading)
        del node.children[-2]


def _token_text(node: Node) -> str:
    first = node.first_token()
    return (first.text or "") if first is not None else ""
