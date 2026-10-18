"""Expressions: operators, calls and member chains, initializers, lambdas, patterns."""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import dataclass, field

from prettycsharp.doc import (
    HARDLINE,
    LINE,
    SOFTLINE,
    Align,
    Doc,
    Fill,
    IfBreak,
    conditional_group,
    group,
    indent,
    join,
    print_doc,
)
from prettycsharp.printer.core import Core
from prettycsharp.syntax import Node

# Binary operator precedence, lowest first. Operators of one level chain.
_PRECEDENCE = {
    "??": 1,
    "||": 2,
    "&&": 3,
    "|": 4,
    "^": 5,
    "&": 6,
    "==": 7,
    "!=": 7,
    "<": 8,
    ">": 8,
    "<=": 8,
    ">=": 8,
    "<<": 9,
    ">>": 9,
    ">>>": 9,
    "+": 10,
    "-": 10,
    "*": 11,
    "/": 11,
    "%": 11,
}

# Values that break across lines by themselves, so an assignment keeps them
# on its own line instead of breaking after the operator.
_SELF_BREAKING = frozenset(
    {
        "invocation_expression",
        "object_creation_expression",
        "implicit_object_creation_expression",
        "anonymous_object_creation_expression",
        "array_creation_expression",
        "implicit_array_creation_expression",
        "collection_expression",
        "initializer_expression",
        "lambda_expression",
        "anonymous_method_expression",
        "switch_expression",
        "with_expression",
        "conditional_expression",
        "binary_expression",
        "query_expression",
        "stackalloc_expression",
        "implicit_stackalloc_expression",
        "tuple_expression",
        "is_pattern_expression",
    }
)

# Values that are laid out as a block of lines after the operator.
_BLOCK_LIKE = frozenset(
    {
        "switch_expression",
        "anonymous_object_creation_expression",
        "collection_expression",
        "initializer_expression",
        "lambda_expression",
        "anonymous_method_expression",
    }
)

_SIMPLE_VALUE_TYPES = frozenset(
    {
        "integer_literal",
        "real_literal",
        "string_literal",
        "verbatim_string_literal",
        "raw_string_literal",
        "character_literal",
        "boolean_literal",
        "null_literal",
        "identifier",
        "predefined_type",
    }
)

_CREATION_TYPES = frozenset(
    {
        "object_creation_expression",
        "implicit_object_creation_expression",
        "array_creation_expression",
        "implicit_array_creation_expression",
        "anonymous_object_creation_expression",
        "with_expression",
        "stackalloc_expression",
        "implicit_stackalloc_expression",
    }
)


@dataclass
class _Link:
    """One step of a member chain: ``.Name`` or ``?.Name`` and what follows it."""

    access: list[Node]
    name: Node | None
    suffixes: list[Node] = field(default_factory=list)

    @property
    def is_call(self) -> bool:
        return any(s.type == "argument_list" for s in self.suffixes)


class Expressions(Core):
    def block(self, block: Node, context: str, head_id: object | None = None) -> Doc:  # pragma: no cover - Statements defines it
        raise NotImplementedError

    # Binary operators ---------------------------------------------------

    def p_binary_expression(self, node: Node) -> Doc:
        return self.binary(node, in_condition=False)

    def binary(self, node: Node, *, in_condition: bool) -> Doc:
        operands, operators = self._flatten_binary(node)
        first = self.print(operands[0])
        rest: list[Doc] = []
        after = self.settings.binary_wrap == "after_operator"
        for op, operand in zip(operators, operands[1:], strict=True):
            if after:
                rest.append([" ", self.tok(op), LINE, self.print(operand)])
            else:
                rest.append([LINE, self.tok(op), " ", self.print(operand)])
        if in_condition:
            return group([first, rest])
        return group([first, indent(rest)])

    def _flatten_binary(self, node: Node) -> tuple[list[Node], list[Node]]:
        op = node.child("operator")
        level = _PRECEDENCE.get(op.text or "", 0) if op is not None else 0
        operands: list[Node] = []
        operators: list[Node] = []
        stack: list[Node] = [node]
        while stack:
            current = stack.pop()
            current_op = current.child("operator") if current.type == "binary_expression" else None
            if (
                current_op is not None
                and _PRECEDENCE.get(current_op.text or "", -1) == level
                and not current.verbatim
            ):
                left = current.child("left")
                right = current.child("right")
                if left is None or right is None:
                    operands.append(current)
                    continue
                # Visit left, then the operator, then right.
                stack.append(right)
                stack.append(_OperatorMarker(current_op))
                stack.append(left)
            elif isinstance(current, _OperatorMarker):
                operators.append(current.op)
            else:
                operands.append(current)
        return operands, operators

    # Conditional expressions ---------------------------------------------

    def p_conditional_expression(self, node: Node) -> Doc:
        condition = node.child("condition")
        consequence = node.child("consequence")
        alternative = node.child("alternative")
        question = node.first_of("?")
        colon = node.first_of(":")
        if condition is None or consequence is None or alternative is None or question is None or colon is None:
            return self.generic(node)
        style = self.settings.ternary_wrap
        cond = self.print(condition)
        yes = self.print(consequence)
        no = self.print(alternative)
        if style == "after":
            return group([cond, " ", self.tok(question), indent([LINE, yes, " ", self.tok(colon), LINE, no])])
        return group(
            [cond, indent([LINE, self.tok(question), " ", yes, LINE, self.tok(colon), " ", no])],
            should_break=style == "always",
        )

    # Assignment ----------------------------------------------------------

    def p_assignment_expression(self, node: Node) -> Doc:
        left = node.child("left")
        op = node.child("operator")
        right = node.child("right")
        if left is None or op is None or right is None:
            return self.generic(node)
        return self.rhs(self.print(left), op, right)

    def rhs(self, left: Doc, op: Node, value: Node) -> Doc:
        """``left op value``, breaking after the operator only for values that cannot break."""
        # A comment at the very end of the value needs no break of its own.
        after, value_doc = self.split_trailing(value, lambda: self.print(value))
        if self.self_breaking(value):
            return [group([left, " ", self.tok(op), " ", value_doc]), after]
        return [group([left, " ", self.tok(op), group(indent([LINE, value_doc]))]), after]

    def self_breaking(self, value: Node) -> bool:
        if value.text is not None and ("\n" in value.text or "\r" in value.text):
            # A multi-line string starts on the operator's line.
            return True
        if value.verbatim:
            return False
        kind = value.type
        if kind in _SELF_BREAKING:
            return True
        if kind == "await_expression":
            awaited = value.named_children()
            return bool(awaited) and self.self_breaking(awaited[-1])
        if kind in ("member_access_expression", "element_access_expression", "conditional_access_expression"):
            return self.chain_calls(value) > 0
        if kind == "cast_expression":
            operand = value.child("value")
            return operand is not None and self.self_breaking(operand)
        return False

    def expression_body(self, clause: Node) -> Doc:
        """`` => expression`` for a member or accessor, without the semicolon."""
        arrow = clause.first_of("=>")
        body = next((c for c in clause.children if c is not arrow), None)
        if arrow is None or body is None:
            return [" ", self.generic(clause)]
        body_doc = self.print(body)
        if self.block_like(body):
            return [" ", self.tok(arrow), " ", body_doc]
        if self.forced_chain(body):
            if self.settings.expression_body_chain == "own_line":
                return [" ", self.tok(arrow), indent([HARDLINE, body_doc])]
            return [" ", self.tok(arrow), " ", body_doc]
        return group([" ", self.tok(arrow), group(indent([LINE, body_doc]))])

    def multiline_value(self, value: Node) -> bool:
        """Whether a value will take several lines whatever the width."""
        if value.text is not None:
            return "\n" in value.text or "\r" in value.text
        if self.forced_chain(value):
            return True
        if value.type in ("lambda_expression", "anonymous_method_expression"):
            body = value.child("body") or value.first_of("block")
            return body is not None and (body.type == "block" or self.multiline_value(body))
        if value.type == "switch_expression":
            return True
        if self.block_like(value):
            return self.initializer_breaks(value) or value.type == "collection_expression" and self._collection_forced(value)
        return False

    def _collection_forced(self, node: Node) -> bool:
        items, _ = self.items_and_commas(node)
        if self.settings.simple_lists_inline and all(len(i) == 1 and _simple_value(_element_value(i[0])) for i in items):
            return False
        return self._forced_initializer([[_element_value(i[0])] for i in items if len(i) == 1])

    def block_like(self, value: Node) -> bool:
        if value.verbatim:
            return False
        if value.type in _BLOCK_LIKE:
            return True
        if value.type in _CREATION_TYPES:
            return value.child("initializer") is not None or value.first_of("initializer_expression") is not None
        return False

    # Member chains -------------------------------------------------------

    def p_invocation_expression(self, node: Node) -> Doc:
        return self.chain(node)

    def p_member_access_expression(self, node: Node) -> Doc:
        return self.chain(node)

    def p_conditional_access_expression(self, node: Node) -> Doc:
        return self.chain(node)

    def p_element_access_expression(self, node: Node) -> Doc:
        return self.chain(node)

    def chain_calls(self, node: Node) -> int:
        _, receiver_suffixes, links = self._flatten_chain(node)
        del receiver_suffixes
        return sum(1 for link in links if link.is_call)

    def forced_chain(self, node: Node) -> bool:
        threshold = self.settings.chain_break_threshold
        if threshold <= 0 or node.type not in (
            "invocation_expression",
            "member_access_expression",
            "conditional_access_expression",
            "element_access_expression",
        ):
            return False
        return self.chain_calls(node) >= threshold

    def _flatten_chain(self, node: Node) -> tuple[Node, list[Node], list[_Link]]:
        links: list[_Link] = []
        suffixes: list[Node] = []
        current = node
        while True:
            if current.verbatim:
                break
            kind = current.type
            if kind == "invocation_expression":
                function = current.child("function")
                arguments = current.child("arguments")
                if function is None or arguments is None:
                    break
                suffixes.append(arguments)
                current = function
            elif kind == "element_access_expression":
                expression = current.child("expression")
                subscript = current.child("subscript")
                if expression is None or subscript is None:
                    break
                suffixes.append(subscript)
                current = expression
            elif kind == "postfix_unary_expression" and current.children and current.children[-1].text == "!":
                suffixes.append(current.children[-1])
                current = current.children[0]
            elif kind == "member_access_expression":
                expression = current.child("expression")
                name = current.child("name")
                access = [c for c in current.children if c is not expression and c is not name]
                if expression is None or name is None or len(access) != 1:
                    break
                links.append(_Link(access, name, list(reversed(suffixes))))
                suffixes = []
                current = expression
            elif kind == "conditional_access_expression":
                condition = current.child("condition")
                question = current.first_of("?")
                binding = current.children[-1]
                if condition is None or question is None or binding is condition or len(current.children) != 3:
                    break
                if binding.type == "member_binding_expression" and len(binding.children) == 2:
                    links.append(_Link([question, binding.children[0]], binding.children[1], list(reversed(suffixes))))
                elif binding.type == "element_binding_expression":
                    # ?[i]: an index on what comes before, behind its question mark.
                    links.append(_Link([question], None, [binding, *reversed(suffixes)]))
                else:
                    break
                suffixes = []
                current = condition
            else:
                break
        links.reverse()
        return current, list(reversed(suffixes)), links

    def chain(self, node: Node) -> Doc:
        receiver, receiver_suffixes, links = self._flatten_chain(node)
        if not links:
            return self._call_or_access(receiver, receiver_suffixes, node)
        head: list[Doc] = [self.print(receiver), *[self.suffix(s) for s in receiver_suffixes]]
        calls = sum(1 for link in links if link.is_call)
        threshold = self.settings.chain_break_threshold
        # Property accesses before the first call stay on the receiver's line.
        first_call = next((i for i, link in enumerate(links) if link.is_call), len(links))
        for link in links[:first_call]:
            head.append(self.link(link))
        rest = links[first_call:]
        if not rest:
            return head
        # Each group ends at a call; accesses after the last call join it.
        groups: list[list[_Link]] = []
        current: list[_Link] = []
        for link in rest:
            current.append(link)
            if link.is_call:
                groups.append(current)
                current = []
        if current:
            groups[-1].extend(current)
        group_docs = [[self.link(link) for link in g] for g in groups]
        if threshold > 0 and calls >= threshold:
            return [head, indent([[HARDLINE, g] for g in group_docs])]
        if threshold <= 0 and len(groups) >= 2:
            return group([head, indent([[SOFTLINE, g] for g in group_docs])])
        return [head, *group_docs]

    def _call_or_access(self, receiver: Node, suffixes: list[Node], node: Node) -> Doc:
        if not suffixes:
            if receiver is node:
                return self.generic(node)
            return self.print(receiver)
        return [self.print(receiver), *[self.suffix(s) for s in suffixes]]

    def link(self, link: _Link) -> Doc:
        parts: list[Doc] = [self.tok(t) for t in link.access]
        if link.name is not None:
            parts.append(self.print(link.name))
        parts.extend(self.suffix(s) for s in link.suffixes)
        return parts

    def suffix(self, node: Node) -> Doc:
        if node.type == "argument_list":
            return self.arguments(node)
        return self.print(node)

    # Arguments -----------------------------------------------------------

    def p_argument_list(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_bracketed_argument_list(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_tuple_expression(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_attribute_argument_list(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_argument(self, node: Node) -> Doc:
        # name: value, out var x, ref y: a space between parts, none before the colon.
        parts: list[Doc] = []
        for i, child in enumerate(node.children):
            if i and child.text != ":":
                parts.append(" ")
            parts.append(self.print(child))
        return parts

    def p_attribute_argument(self, node: Node) -> Doc:
        return self.p_argument(node)

    def arguments(self, node: Node) -> Doc:
        """``(a, b)`` or ``[a, b]``: on one line, or one argument per line."""
        if len(node.children) < 2:
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        items, commas = self.items_and_commas(node)
        if not items:
            return group([self.tok(open_tok), self.closing(close_tok, SOFTLINE)])
        docs = [self.print_item(item) for item in items]
        for i, comma in enumerate(commas):
            if i < len(docs):
                docs[i] = [docs[i], self.tok(comma)]
        return self.argument_layout(open_tok, docs, close_tok, items)

    def argument_layout(self, open_tok: Node, docs: list[Doc], close_tok: Node, items: Sequence[Sequence[Node]]) -> Doc:
        style = self.settings.argument_wrap
        open_doc = self.tok(open_tok)
        hugging_close = self.closing(close_tok, "")
        if style == "fill":
            parts: list[Doc] = []
            for i, doc in enumerate(docs):
                if i:
                    parts.append(LINE)
                parts.append(doc)
            return group([open_doc, indent([SOFTLINE, Fill(parts)]), hugging_close])
        if style == "align":
            return group([open_doc, Align(-1, join(LINE, docs)), hugging_close])
        if style == "one_per_line_close_on_last":
            expanded: Doc = group([open_doc, indent([SOFTLINE, join(LINE, docs)]), hugging_close])
        else:
            expanded = group([open_doc, indent([SOFTLINE, join(LINE, docs)]), self.closing(close_tok, SOFTLINE)])
        if self.settings.lambda_body == "hug" and not close_tok.leading and self._can_hug(items):
            close_doc = self.tok(close_tok)
            last = items[-1][0]
            hugged_last = group(self.print(last), should_break=True)
            if len(items) - 1 < len(docs) and isinstance(docs[-1], list) and len(docs[-1]) == 2:
                # A trailing comma after the hugged argument stays with it.
                hugged_last = group([hugged_last, docs[-1][1]], should_break=True)
            head = docs[:-1]
            flat = [open_doc, join(" ", docs), close_doc]
            hugged = [open_doc, join(" ", [*head, hugged_last]), close_doc]
            return conditional_group([flat, hugged, expanded])
        return expanded

    def _can_hug(self, items: Sequence[Sequence[Node]]) -> bool:
        if not items or any(len(item) != 1 for item in items):
            return False
        last = items[-1][0]
        target = last.children[-1] if last.type == "argument" and last.children else last
        if not self.huggable(target):
            return False
        for item in items[:-1]:
            node = item[0]
            if any(t.leading or t.trailing for t in node.tokens()):
                return False
            if any(self.huggable(n) for n in _descendants(node)):
                return False
        return not any(t.leading for t in last.tokens())

    def huggable(self, node: Node) -> bool:
        if node.verbatim:
            return False
        if node.type in ("lambda_expression", "anonymous_method_expression"):
            body = node.child("body") or node.first_of("block")
            if body is None:
                return False
            # A block, or a body that takes several lines anyway, such as a
            # broken member chain, hangs off the call's line.
            return body.type == "block" or self.huggable(body) or self.forced_chain(body)
        if node.type in _CREATION_TYPES:
            return self.block_like(node) and self.initializer_breaks(node)
        return node.type == "switch_expression"

    def print_item(self, item: Sequence[Node]) -> Doc:
        if len(item) == 1:
            return self.print(item[0])
        return self.generic_sequence(item)

    def generic_sequence(self, nodes: Sequence[Node]) -> Doc:
        parts: list[Doc] = []
        previous: Node | None = None
        for node in nodes:
            if previous is not None and self.space_between(previous, node):
                parts.append(" ")
            parts.append(self.print(node))
            previous = node
        return parts

    def items_and_commas(self, node: Node) -> tuple[list[list[Node]], list[Node]]:
        items = self.separated(node)
        return items, self.separators(node)

    # Creation and initializers ---------------------------------------------

    def p_object_creation_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def p_implicit_object_creation_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def p_array_creation_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def p_implicit_array_creation_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def p_stackalloc_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def p_implicit_stackalloc_expression(self, node: Node) -> Doc:
        return self.creation(node)

    def creation(self, node: Node) -> Doc:
        parts: list[Doc] = []
        previous: Node | None = None
        for child in node.children:
            if child.type == "initializer_expression":
                parts.append(self.initializer(child))
            else:
                if previous is not None and self._space_in_creation(previous, child):
                    parts.append(" ")
                parts.append(self.print(child))
            previous = child
        return parts

    def _space_in_creation(self, previous: Node, child: Node) -> bool:
        if child.type in ("argument_list", "array_rank_specifier", "bracketed_argument_list"):
            return False
        if previous.text in ("new", "stackalloc"):
            # new() and new[] stay closed up; new Foo takes a space.
            return child.text not in ("(", "[") and child.type not in ("argument_list",)
        return self.space_between(previous, child)

    def initializer_breaks(self, node: Node) -> bool:
        init = node if node.type == "initializer_expression" else (
            node.child("initializer") or node.first_of("initializer_expression")
        )
        if init is None:
            if node.type == "anonymous_object_creation_expression":
                items = self.separated(_braced_part(node))
                return len(items) >= max(self.settings.initializer_break_threshold, 1)
            return False
        items, _ = self.items_and_commas(init)
        return self._forced_initializer(items)

    def _forced_initializer(self, items: Sequence[Sequence[Node]]) -> bool:
        threshold = self.settings.initializer_break_threshold
        if not items:
            return False
        if self.settings.simple_lists_inline and all(len(i) == 1 and _simple_value(i[0]) for i in items):
            return False
        return threshold > 0 and len(items) >= threshold

    def initializer(self, node: Node, *, leading_space: bool = True) -> Doc:
        """``{ a, b }`` after a creation: inline, or a braced block of lines."""
        if len(node.children) < 2:
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        items, commas = self.items_and_commas(node)
        if not items:
            return group([" " if leading_space else "", self.tok(open_tok), self.closing(close_tok, LINE)])
        docs = self._comma_docs(items, commas, may_add=True)
        simple = self.settings.simple_lists_inline and all(len(i) == 1 and _simple_value(i[0]) for i in items)
        force = self._forced_initializer(items)
        # Allman: a broken initializer's brace takes a line of its own.
        before: Doc = LINE if (self.settings.brace_style == "allman" and leading_space) else (" " if leading_space else "")
        if simple:
            body = self._packed(docs, items, commas)
            return group([before, self.tok(open_tok), indent([LINE, body]), self.closing(close_tok, LINE)])
        return group(
            [before, self.tok(open_tok), indent([LINE, join(LINE, docs)]), self.closing(close_tok, LINE)],
            should_break=force,
        )

    def _packed(self, docs: list[Doc], items: Sequence[Sequence[Node]], commas: Sequence[Node]) -> Doc:
        """Simple values as many to a line as fit; one to a line when any has a comment."""
        nodes = [n for item in items for n in item] + list(commas)
        if any(t.leading or t.trailing for n in nodes for t in n.tokens()):
            return join(LINE, docs)
        return Fill(_fill_parts(docs))

    def _comma_docs(
        self, items: Sequence[Sequence[Node]], commas: Sequence[Node], *, may_add: bool = False
    ) -> list[Doc]:
        """Each item with the comma after it; ``may_add`` lets trailing_commas = add add one."""
        docs: list[Doc] = []
        last = len(items) - 1
        for i, item in enumerate(items):
            if i < len(commas) and i < last:
                docs.append([self.print_item(item), self.tok(commas[i])])
            elif i < len(commas):
                # A trailing comma that was kept: printed only when broken.
                docs.append([self.print_item(item), IfBreak(self.tok(commas[i]), "")])
            elif i == last and may_add and self.settings.trailing_commas == "add" and len(item) == 1:
                # The added comma goes before a comment at the end of the item.
                after, doc = self.split_trailing(item[0], functools.partial(self.print_item, item))
                docs.append([doc, IfBreak(",", ""), after])
            else:
                docs.append(self.print_item(item))
        return docs

    def p_initializer_expression(self, node: Node) -> Doc:
        # A nested initializer, such as B = { 1, 2 }, or one in an array.
        return self.initializer(node, leading_space=False)

    def p_collection_expression(self, node: Node) -> Doc:
        if len(node.children) < 2:
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        items, commas = self.items_and_commas(node)
        if not items:
            return group([self.tok(open_tok), self.closing(close_tok, SOFTLINE)])
        docs = self._comma_docs(items, commas, may_add=True)
        simple = self.settings.simple_lists_inline and all(
            len(i) == 1 and _simple_value(_element_value(i[0])) for i in items
        )
        if simple:
            body = self._packed(docs, items, commas)
            return group([self.tok(open_tok), indent([SOFTLINE, body]), self.closing(close_tok, SOFTLINE)])
        force = self._forced_initializer([[_element_value(i[0])] for i in items if len(i) == 1])
        return group(
            [SOFTLINE, self.tok(open_tok), indent([LINE, join(LINE, docs)]), self.closing(close_tok, LINE)],
            should_break=force,
        )

    def p_collection_element(self, node: Node) -> Doc:
        return self.generic(node)

    def p_anonymous_object_creation_expression(self, node: Node) -> Doc:
        new = node.first_of("new")
        open_tok = node.first_of("{")
        close_tok = node.children[-1] if node.children else None
        if new is None or open_tok is None or close_tok is None or close_tok.text != "}":
            return self.generic(node)
        braced = _braced_part(node)
        items, commas = self.items_and_commas(braced)
        if not items:
            return [self.tok(new), " ", self.tok(open_tok), " ", self.tok(close_tok)]
        docs = self._comma_docs(items, commas, may_add=True)
        threshold = self.settings.initializer_break_threshold
        force = threshold > 0 and len(items) >= threshold
        before: Doc = LINE if self.settings.brace_style == "allman" else " "
        return group(
            [self.tok(new), before, self.tok(open_tok), indent([LINE, join(LINE, docs)]), self.closing(close_tok, LINE)],
            should_break=force,
        )

    def p_with_expression(self, node: Node) -> Doc:
        open_tok = node.first_of("{")
        close_tok = node.children[-1] if node.children else None
        with_tok = node.first_of("with")
        if open_tok is None or close_tok is None or with_tok is None or close_tok.text != "}":
            return self.generic(node)
        expression = node.children[0]
        braced = _braced_part(node)
        items, commas = self.items_and_commas(braced)
        # with_initializer wraps the assignments in some grammar versions.
        if len(items) == 1 and len(items[0]) == 1 and items[0][0].type == "with_initializer":
            inner = items[0][0]
            items = [[c for c in group_] for group_ in _split_commas(inner.children)]
            commas = [c for c in inner.children if c.text == "," and not c.named]
        head = [self.print(expression), " ", self.tok(with_tok)]
        if not items:
            return group([head, " ", self.tok(open_tok), self.closing(close_tok, LINE)])
        docs = self._comma_docs(items, commas, may_add=True)
        force = self._forced_initializer(items)
        before: Doc = LINE if self.settings.brace_style == "allman" else " "
        return group([head, before, self.tok(open_tok), indent([LINE, join(LINE, docs)]), self.closing(close_tok, LINE)], should_break=force)

    def p_with_initializer(self, node: Node) -> Doc:
        return self.generic_sequence(node.children)

    # Lambdas -------------------------------------------------------------

    def p_lambda_expression(self, node: Node) -> Doc:
        arrow = node.first_of("=>")
        body = node.child("body")
        if arrow is None or body is None:
            return self.generic(node)
        comments = self.hoist_leading(node.children[0]) if body.type == "block" else ""
        head: list[Doc] = []
        previous: Node | None = None
        for child in node.children:
            if child is arrow:
                break
            if previous is not None:
                head.append(" ")
            head.append(self.print(child))
            previous = child
        if body.type == "block":
            head_id = object()
            return [comments, group([head, " ", self.tok(arrow)], id=head_id), self.block(body, "lambda", head_id)]
        body_doc = self.print(body)
        if self.self_breaking(body) or self.block_like(body):
            return [head, " ", self.tok(arrow), " ", body_doc]
        return group([head, " ", self.tok(arrow), group(indent([LINE, body_doc]))])

    def p_anonymous_method_expression(self, node: Node) -> Doc:
        block = node.first_of("block")
        if block is None or node.children[-1] is not block:
            return self.generic(node)
        head = self.generic_sequence(node.children[:-1])
        return [head, self.block(block, "lambda")]

    # Switch expressions ---------------------------------------------------

    def p_switch_expression(self, node: Node) -> Doc:
        switch = node.first_of("switch")
        open_tok = node.first_of("{")
        close_tok = node.children[-1] if node.children else None
        if switch is None or open_tok is None or close_tok is None or close_tok.text != "}":
            return self.generic(node)
        governing = node.children[0]
        arms = [c for c in node.children if c.type == "switch_expression_arm"]
        commas = [c for c in node.children if c.text == "," and not c.named]
        head = [self.print(governing), " ", self.tok(switch)]
        if not arms:
            return group([head, " ", self.tok(open_tok), self.closing(close_tok, LINE)])
        comments: list[Doc] = []
        lefts: list[Doc] = []
        rights: list[Doc] = []
        widths: list[int | None] = []
        for arm in arms:
            above, (left, right) = self.split_leading(arm, functools.partial(self._arm_parts, arm))
            comments.append(above)
            lefts.append(left)
            rights.append(right)
            widths.append(self.flat_width(left) if self.settings.align_switch_arms else None)
        known = [w for w in widths if w is not None]
        target = max(known) if known else 0
        lines: list[Doc] = []
        for i in range(len(arms)):
            pad = ""
            if widths[i] is not None and len(known) > 1:
                pad = " " * (target - (widths[i] or 0))
            doc: list[Doc] = [comments[i], lefts[i], pad, rights[i]]
            comma = commas[i] if i < len(commas) else None
            if comma is not None and (i < len(arms) - 1 or self.settings.trailing_commas != "remove"):
                doc.append(self.tok(comma))
            elif comma is None and i < len(arms) - 1:
                doc.append(",")
            lines.append(doc)
        return [
            head,
            self.open_brace("statement"),
            self.tok(open_tok),
            indent([HARDLINE, join(HARDLINE, lines)]),
            self.close_comments(close_tok),
            HARDLINE,
            self.tok(close_tok, leading=False),
        ]

    def _arm_parts(self, arm: Node) -> tuple[Doc, Doc]:
        arrow = arm.first_of("=>")
        if arrow is None:
            return self.generic(arm), ""
        index = arm.children.index(arrow)
        left = self.generic_sequence(arm.children[:index])
        value = arm.children[index + 1 :]
        if len(value) != 1:
            return left, [" ", self.tok(arrow), " ", self.generic_sequence(value)]
        value_node = value[0]
        if self.self_breaking(value_node) or self.block_like(value_node):
            return left, [" ", self.tok(arrow), " ", self.print(value_node)]
        return left, group([" ", self.tok(arrow), group(indent([LINE, self.print(value_node)]))])

    def flat_width(self, doc: Doc) -> int | None:
        """The width of a document printed on one line, or None if it cannot be."""
        text = print_doc(doc, 1_000_000)
        if "\n" in text or "\r" in text:
            return None
        return len(text)

    # Operators and small forms ---------------------------------------------

    def p_prefix_unary_expression(self, node: Node) -> Doc:
        if len(node.children) != 2:
            return self.generic(node)
        op, operand = node.children
        return self.join_tokens([(op, self.tok(op)), (operand, self.print(operand))])

    def p_postfix_unary_expression(self, node: Node) -> Doc:
        if len(node.children) != 2:
            return self.generic(node)
        operand, op = node.children
        if op.text == "!":
            return self.chain(node)
        return self.join_tokens([(operand, self.print(operand)), (op, self.tok(op))])

    def p_cast_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_parenthesized_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_await_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_throw_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_ref_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_declaration_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_as_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_is_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_is_pattern_expression(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_range_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_typeof_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_sizeof_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_default_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_checked_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_makeref_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_member_binding_expression(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_element_binding_expression(self, node: Node) -> Doc:
        return self.arguments(node)

    # Patterns ------------------------------------------------------------

    def p_property_pattern_clause(self, node: Node) -> Doc:
        if len(node.children) < 2:
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        items, commas = self.items_and_commas(node)
        if not items:
            return group([self.tok(open_tok), self.closing(close_tok, LINE)])
        docs = self._comma_docs(items, commas)
        return group([self.tok(open_tok), indent([LINE, join(LINE, docs)]), self.closing(close_tok, LINE)])

    def p_positional_pattern_clause(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_list_pattern(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_tuple_pattern(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_parenthesized_variable_designation(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_subpattern(self, node: Node) -> Doc:
        colon = node.first_of(":")
        if colon is None:
            return self.generic(node)
        index = node.children.index(colon)
        return [
            self.generic_sequence(node.children[:index]),
            self.tok(colon),
            " ",
            self.generic_sequence(node.children[index + 1 :]),
        ]

    def p_relational_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_and_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_or_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_negated_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_declaration_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_recursive_pattern(self, node: Node) -> Doc:
        parts: list[Doc] = []
        previous: Node | None = None
        for child in node.children:
            if previous is not None and not (child.type == "positional_pattern_clause" and previous.named):
                parts.append(" ")
            parts.append(self.print(child))
            previous = child
        return parts

    def p_var_pattern(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_when_clause(self, node: Node) -> Doc:
        return self.spaced(node.children)

    # Queries -------------------------------------------------------------

    def p_query_expression(self, node: Node) -> Doc:
        segments: list[list[Node]] = []
        for child in node.children:
            # A clause starts a line; `into name` continues the clause before it.
            if child.type.endswith("_clause") or not segments:
                segments.append([child])
            else:
                segments[-1].append(child)
        docs = [self.generic_sequence(segment) for segment in segments]
        if len(docs) < 2:
            return docs
        return group([docs[0], indent([[LINE, d] for d in docs[1:]])])

    # Names and types ------------------------------------------------------

    def p_generic_name(self, node: Node) -> Doc:
        return [self.print(c) for c in node.children]

    def p_type_argument_list(self, node: Node) -> Doc:
        return self.angle_list(node)

    def p_type_parameter_list(self, node: Node) -> Doc:
        return self.angle_list(node)

    def angle_list(self, node: Node) -> Doc:
        if len(node.children) < 2:
            return self.generic(node)
        inner = node.children[1:-1]
        if all(c.text == "," and not c.named for c in inner):
            # An open generic type, typeof(Dictionary<,>): only commas.
            return self.join_tokens([(c, self.print(c)) for c in node.children])
        items, commas = self.items_and_commas(node)
        docs: list[Doc] = []
        for i, item in enumerate(items):
            doc = self.print_item(item)
            if i < len(commas):
                doc = [doc, self.tok(commas[i])]
            docs.append(doc)
        return [self.tok(node.children[0]), join(" ", docs), self.tok(node.children[-1])]

    def p_type_parameter(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_qualified_name(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_alias_qualified_name(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_array_type(self, node: Node) -> Doc:
        # A rank follows its element type tight, nullable or not: `object?[]`.
        return [self.print(c) for c in node.children]

    def p_array_rank_specifier(self, node: Node) -> Doc:
        parts: list[Doc] = []
        for child in node.children:
            parts.append(self.print(child))
            if child.text == "," and child is not node.children[-2] and node.children[node.children.index(child) + 1].text not in (",", "]"):
                parts.append(" ")
        return parts

    def p_nullable_type(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_pointer_type(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_tuple_type(self, node: Node) -> Doc:
        return self.arguments(node)

    def p_tuple_element(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_ref_type(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_scoped_type(self, node: Node) -> Doc:
        return self.spaced(node.children)

    def p_explicit_interface_specifier(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_expression_element(self, node: Node) -> Doc:
        return self.generic(node)

    def p_spread_element(self, node: Node) -> Doc:
        # Visual Studio spaces a spread, `[.. items]`, unlike a range, `items[..2]`.
        return self.spaced(node.children)


class _OperatorMarker(Node):
    """A placeholder in the binary-expression flattening stack."""

    def __init__(self, op: Node) -> None:
        super().__init__(type="__operator__")
        self.op = op


def _descendants(node: Node) -> list[Node]:
    out: list[Node] = []
    stack = list(node.children)
    while stack:
        current = stack.pop()
        out.append(current)
        stack.extend(current.children)
    return out


def _simple_value(node: Node) -> bool:
    if node.type in _SIMPLE_VALUE_TYPES:
        return True
    if node.type == "prefix_unary_expression" and len(node.children) == 2:
        return node.children[0].text in ("-", "+") and node.children[1].type in ("integer_literal", "real_literal")
    if node.type in ("member_access_expression", "qualified_name"):
        return all(c.type in ("identifier", "member_access_expression", "qualified_name") or c.text == "." for c in node.children)
    return False


def _element_value(node: Node) -> Node:
    # collection_element > expression_element > value; ..value spreads a value.
    while True:
        if node.type in ("collection_element", "expression_element") and len(node.children) == 1:
            node = node.children[0]
        elif node.type == "spread_element" and len(node.children) == 2:
            node = node.children[1]
        else:
            return node


def _fill_parts(docs: Sequence[Doc]) -> list[Doc]:
    parts: list[Doc] = []
    for i, doc in enumerate(docs):
        if i:
            parts.append(LINE)
        parts.append(doc)
    return parts


def _braced_part(node: Node) -> Node:
    """A stand-in node holding ``{`` ... ``}`` of a node, for splitting at commas."""
    open_index = next(i for i, c in enumerate(node.children) if c.text == "{")
    holder = Node(type="braced")
    holder.children = node.children[open_index:]
    return holder


def _split_commas(children: Sequence[Node]) -> list[list[Node]]:
    groups: list[list[Node]] = [[]]
    for child in children:
        if child.text == "," and not child.named:
            groups.append([])
        else:
            groups[-1].append(child)
    return [g for g in groups if g]
