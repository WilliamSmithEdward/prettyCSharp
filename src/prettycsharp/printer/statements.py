"""Statements and blocks."""

from __future__ import annotations

import functools
from collections.abc import Callable, Sequence

from prettycsharp.doc import HARDLINE, LINE, SOFTLINE, Doc, conditional_group, group, indent, join
from prettycsharp.printer.expressions import Expressions
from prettycsharp.syntax import DIRECTIVE_TYPES, Node, token

# (left side, operator, value, what ends the item) for an alignable item.
Splitter = Callable[[Node], "tuple[Doc, Node, Node, Doc] | None"]

BLOCK_STATEMENTS = frozenset(
    {
        "if_statement",
        "for_statement",
        "foreach_statement",
        "while_statement",
        "do_statement",
        "switch_statement",
        "try_statement",
        "using_statement",
        "lock_statement",
        "fixed_statement",
        "checked_statement",
        "unsafe_statement",
        "block",
    }
)

# Statements whose body is an embedded statement printed after a header.
_EMBEDDED_PARENTS = frozenset(
    {"if_statement", "for_statement", "foreach_statement", "while_statement", "using_statement", "lock_statement", "fixed_statement"}
)


class Statements(Expressions):
    # Blocks ---------------------------------------------------------------

    def block(self, block: Node, context: str, head_id: object | None = None) -> Doc:
        """A block after a header: the brace's line break or space, then the braces.

        ``head_id`` names the header's group, for headers whose empty body
        moves to its own line when the header spans lines."""
        if self.is_empty_block(block) and self.settings.empty_bodies == "inline":
            return [self.after_header(head_id), self.block_braces(block)]
        return [self.open_brace(context), self.block_braces(block)]

    def is_empty_block(self, block: Node) -> bool:
        if len(block.children) != 2 or block.verbatim:
            return False
        close = block.children[-1]
        return not close.leading and not block.children[0].trailing

    def block_braces(self, block: Node) -> Doc:
        if block.verbatim or len(block.children) < 2:
            return self.print(block)
        open_tok = block.children[0]
        close_tok = block.children[-1]
        items = block.children[1:-1]
        if not items and not close_tok.leading:
            if self.settings.empty_bodies == "inline" or open_tok.trailing:
                return [self.tok(open_tok), " ", self.tok(close_tok)]
            return [self.tok(open_tok), HARDLINE, self.tok(close_tok)]
        body: Doc = ""
        if items:
            body = indent([HARDLINE, self.statements(items)])
        return [self.tok(open_tok), body, self.close_comments(close_tok), HARDLINE, self.tok(close_tok, leading=False)]

    def p_block(self, node: Node) -> Doc:
        return self.block_braces(node)

    def statements(self, items: Sequence[Node]) -> Doc:
        return self.print_list(items, self.statement_blank, aligned=self.aligned_assignments(items))

    def statement_blank(self, previous: Node, item: Node) -> bool:
        if self.tight_directive(previous, item):
            return False
        if previous.type in DIRECTIVE_TYPES or item.type in DIRECTIVE_TYPES:
            return self.has_blank_before(item)
        if self.settings.blank_lines_around_blocks and (self.is_block_statement(previous) or self.is_block_statement(item)):
            return self.settings.max_blank_lines > 0
        return self.has_blank_before(item)

    def is_block_statement(self, node: Node) -> bool:
        if node.type == "global_statement" and node.children:
            node = node.children[0]
        if node.type == "labeled_statement" and node.children:
            node = node.children[-1]
        if node.type in BLOCK_STATEMENTS:
            return True
        if node.type == "local_function_statement":
            return node.child("body") is not None and node.child("body").type == "block"  # type: ignore[union-attr]
        return False

    # Embedded statements ------------------------------------------------

    def embedded(self, body: Node, context_token: Node, parent: Node) -> Doc:
        """The statement after a header such as ``if (...)``."""
        if body.type == "block" and not body.verbatim:
            return self.block(body, "statement")
        if body.type == "empty_statement":
            return self.print(body)
        if body.type in ("using_statement", "fixed_statement") and body.type == parent.type:
            # Stacked using or fixed statements share one body.
            return [HARDLINE, self.print(body)]
        statement = self.print(body)
        if self.settings.braces == "single_line_only":
            braced = self._braced(body)
            # The braced form prints in break mode, so its own groups can still break.
            return conditional_group([[" ", statement], group(braced, should_break=True), braced])
        same_line = (
            body.line >= 0
            and context_token.end_line >= 0
            and body.line == context_token.end_line
            and not _starts_with_comment(body)
        )
        if same_line:
            return group(indent([LINE, statement]))
        return indent([HARDLINE, statement])

    def _braced(self, body: Node) -> Doc:
        open_tok = token("{")
        close_tok = token("}")
        return [self.open_brace("statement"), self.tok(open_tok), indent([HARDLINE, self.print(body)]), HARDLINE, self.tok(close_tok)]

    def continuation(self, before: Node, keyword: Node) -> Doc:
        """What separates ``}`` from ``else``, ``catch``, ``finally`` or a do loop's ``while``."""
        style = self.settings.continuation_keywords
        braced = before.type == "block" or (before.type in ("catch_clause", "finally_clause"))
        if keyword.leading:
            # A comment before the keyword needs a line of its own.
            style = "blank_line" if style == "blank_line" else "new_line"
        if style == "same_line" and braced and self.settings.brace_style != "allman":
            return " "
        if style == "blank_line" and self.settings.max_blank_lines > 0:
            return [HARDLINE, HARDLINE]
        return HARDLINE

    # Conditions ---------------------------------------------------------

    def condition(self, open_tok: Node, condition: Node, close_tok: Node) -> Doc:
        if (
            self.settings.binary_wrap == "before_operator_paren_own_line"
            and condition.type == "binary_expression"
            and not condition.verbatim
        ):
            return group(
                [
                    self.tok(open_tok),
                    indent([SOFTLINE, self.binary(condition, in_condition=True)]),
                    SOFTLINE,
                    self.tok(close_tok),
                ]
            )
        return [self.tok(open_tok), self.print(condition), self.tok(close_tok)]

    # if / else ----------------------------------------------------------

    def p_if_statement(self, node: Node) -> Doc:
        keyword = node.first_of("if")
        open_tok = node.first_of("(")
        condition = node.child("condition")
        close_tok = node.first_of(")")
        consequence = node.child("consequence")
        if keyword is None or open_tok is None or condition is None or close_tok is None or consequence is None:
            return self.generic(node)
        parts: list[Doc] = [self.tok(keyword), " ", self.condition(open_tok, condition, close_tok)]
        parts.append(self.embedded(consequence, close_tok, node))
        else_tok = node.first_of("else")
        alternative = node.child("alternative")
        if else_tok is not None and alternative is not None:
            parts.append(self.continuation(consequence, else_tok))
            parts.append(self.tok(else_tok))
            if alternative.type == "if_statement" and not alternative.verbatim and not _starts_with_comment(alternative):
                parts.append(" ")
                parts.append(self.print(alternative))
            else:
                parts.append(self.embedded(alternative, else_tok, node))
        return parts

    # Loops --------------------------------------------------------------

    def p_while_statement(self, node: Node) -> Doc:
        keyword = node.first_of("while")
        open_tok = node.first_of("(")
        condition = node.child("condition")
        close_tok = node.first_of(")")
        body = node.child("body") or (node.children[-1] if node.children else None)
        if keyword is None or open_tok is None or condition is None or close_tok is None or body is None:
            return self.generic(node)
        return [self.tok(keyword), " ", self.condition(open_tok, condition, close_tok), self.embedded(body, close_tok, node)]

    def p_do_statement(self, node: Node) -> Doc:
        do = node.first_of("do")
        body = node.child("body")
        keyword = node.first_of("while")
        open_tok = node.first_of("(")
        condition = node.child("condition")
        close_tok = node.first_of(")")
        semicolon = node.first_of(";")
        if None in (do, body, keyword, open_tok, condition, close_tok, semicolon):
            return self.generic(node)
        assert do and body and keyword and open_tok and condition and close_tok and semicolon
        if body.type == "block":
            body_doc = self.block(body, "statement")
        else:
            body_doc = indent([HARDLINE, self.print(body)])
        return [
            self.tok(do),
            body_doc,
            self.continuation(body, keyword),
            self.tok(keyword),
            " ",
            self.condition(open_tok, condition, close_tok),
            self.tok(semicolon),
        ]

    def p_for_statement(self, node: Node) -> Doc:
        keyword = node.first_of("for")
        open_tok = node.first_of("(")
        close_index = _last_index(node.children, ")")
        if keyword is None or open_tok is None or close_index is None:
            return self.generic(node)
        close_tok = node.children[close_index]
        body = node.children[close_index + 1] if close_index + 1 < len(node.children) else None
        open_index = node.children.index(open_tok)
        header_children = node.children[open_index + 1 : close_index]
        empty = not any(child.named for child in header_children)
        inner: list[Doc] = []
        pending_space = False
        for child in header_children:
            if pending_space:
                inner.append(LINE)
            if child.text in (";", ",") and not child.named:
                inner.append(self.tok(child))
                pending_space = True
                continue
            pending_space = False
            inner.append(self.print(child))
        header = group(
            [
                self.tok(keyword), " ", self.tok(open_tok), indent([SOFTLINE, inner]),
                LINE if empty else SOFTLINE, self.tok(close_tok),
            ]
        )
        if body is None:
            return header
        return [header, self.embedded(body, close_tok, node)]

    def p_foreach_statement(self, node: Node) -> Doc:
        open_tok = node.first_of("(")
        close_index = _last_index(node.children, ")")
        if open_tok is None or close_index is None:
            return self.generic(node)
        open_index = node.children.index(open_tok)
        close_tok = node.children[close_index]
        keywords = self.spaced(node.children[:open_index])
        inner = self.spaced(node.children[open_index + 1 : close_index])
        body = node.children[close_index + 1] if close_index + 1 < len(node.children) else None
        header = [keywords, " ", self.tok(open_tok), inner, self.tok(close_tok)]
        if body is None:
            return header
        return [header, self.embedded(body, close_tok, node)]

    # Other statements with a header and a body ---------------------------

    def _headed(self, node: Node) -> Doc:
        """keyword(s) ``(...)`` body: using, lock, fixed."""
        open_tok = node.first_of("(")
        close_index = _last_index(node.children, ")")
        if open_tok is None or close_index is None:
            return self.generic(node)
        open_index = node.children.index(open_tok)
        close_tok = node.children[close_index]
        keywords = self.spaced(node.children[:open_index])
        inner = self.generic_sequence(node.children[open_index + 1 : close_index])
        body = node.children[close_index + 1] if close_index + 1 < len(node.children) else None
        header = [keywords, " ", self.tok(open_tok), inner, self.tok(close_tok)]
        if body is None:
            return header
        return [header, self.embedded(body, close_tok, node)]

    def p_using_statement(self, node: Node) -> Doc:
        return self._headed(node)

    def p_lock_statement(self, node: Node) -> Doc:
        return self._headed(node)

    def p_fixed_statement(self, node: Node) -> Doc:
        return self._headed(node)

    def p_checked_statement(self, node: Node) -> Doc:
        return self._keyword_block(node)

    def p_unsafe_statement(self, node: Node) -> Doc:
        return self._keyword_block(node)

    def _keyword_block(self, node: Node) -> Doc:
        block = node.children[-1] if node.children else None
        if block is None or block.type != "block":
            return self.generic(node)
        return [self.spaced(node.children[:-1]), self.block(block, "statement")]

    # switch -------------------------------------------------------------

    def p_switch_statement(self, node: Node) -> Doc:
        body = node.child("body")
        if body is None or body.type != "switch_body":
            return self.generic(node)
        index = node.children.index(body)
        keyword = node.children[0]
        # switch (x), or switch (a, b) where the tuple brings its own parentheses.
        governing = self.join_tokens([(c, self.print(c)) for c in node.children[1:index]])
        return [self.tok(keyword), " ", governing, self.open_brace("statement"), self.print(body)]

    def p_switch_body(self, node: Node) -> Doc:
        if len(node.children) < 2:
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        sections = node.children[1:-1]
        body: Doc = ""
        if sections:
            lines = [HARDLINE, self.print_list(sections, self.section_blank)]
            # Case labels sit one level in, or flush with switch.
            body = indent(lines) if self.settings.switch_case_indent else lines
        comments = self.close_comments(close_tok)
        # Trailing comments belong at the final section's statement level.
        if self.settings.switch_case_indent and any(section.type == "switch_section" for section in sections):
            comments = indent(comments)
        return [self.tok(open_tok), body, comments, HARDLINE, self.tok(close_tok, leading=False)]

    def section_blank(self, previous: Node, item: Node) -> bool:
        if self.tight_directive(previous, item):
            return False
        if previous.type in DIRECTIVE_TYPES or item.type in DIRECTIVE_TYPES:
            return self.has_blank_before(item)
        if not self.settings.switch_case_blank_lines or self.settings.max_blank_lines == 0:
            return False
        return bool(self._section_statements(previous))

    def _section_statements(self, section: Node) -> list[Node]:
        colon = next((i for i, c in enumerate(section.children) if c.text == ":" and not c.named), None)
        if colon is None:
            return []
        return section.children[colon + 1 :]

    def p_switch_section(self, node: Node) -> Doc:
        colon = next((i for i, c in enumerate(node.children) if c.text == ":" and not c.named), None)
        if colon is None:
            return self.generic(node)
        label = [self.spaced(node.children[:colon]), self.tok(node.children[colon])]
        statements = node.children[colon + 1 :]
        if not statements:
            return label
        body = [HARDLINE, self.statements(statements)]
        return [label, indent(body)]

    # try ----------------------------------------------------------------

    def p_try_statement(self, node: Node) -> Doc:
        keyword = node.first_of("try")
        body = node.child("body")
        if keyword is None or body is None:
            return self.generic(node)
        parts: list[Doc] = [self.tok(keyword), self.block(body, "statement")]
        previous: Node = body
        for clause in node.children:
            if clause.type not in ("catch_clause", "finally_clause"):
                continue
            first = clause.first_token()
            if first is None:
                return self.generic(node)
            parts.append(self.continuation(previous, first))
            parts.append(self.print(clause))
            previous = clause
        return parts

    def p_catch_clause(self, node: Node) -> Doc:
        block = node.children[-1] if node.children else None
        if block is None or block.type != "block":
            return self.generic(node)
        comments = self.hoist_leading(node.children[0])
        head_id = object()
        return [comments, group(self.spaced(node.children[:-1]), id=head_id), self.block(block, "statement", head_id)]

    def p_finally_clause(self, node: Node) -> Doc:
        return self.p_catch_clause(node)

    def p_catch_declaration(self, node: Node) -> Doc:
        if len(node.children) < 2:
            return self.generic(node)
        return [self.tok(node.children[0]), self.spaced(node.children[1:-1]), self.tok(node.children[-1])]

    def p_catch_filter_clause(self, node: Node) -> Doc:
        keyword = node.first_of("when")
        open_tok = node.first_of("(")
        close_tok = node.children[-1] if node.children else None
        if keyword is None or open_tok is None or close_tok is None or close_tok.text != ")":
            return self.generic(node)
        inner = node.children[node.children.index(open_tok) + 1 : -1]
        if len(inner) != 1:
            return self.generic(node)
        return [self.tok(keyword), " ", self.condition(open_tok, inner[0], close_tok)]

    # Simple statements --------------------------------------------------

    def p_expression_statement(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_return_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def p_throw_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def p_yield_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def p_goto_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def p_break_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def p_continue_statement(self, node: Node) -> Doc:
        return self._keyword_statement(node)

    def _keyword_statement(self, node: Node) -> Doc:
        parts: list[Doc] = []
        for i, child in enumerate(node.children):
            if i and child.text != ";":
                parts.append(" ")
            parts.append(self.print(child))
        return parts

    def p_empty_statement(self, node: Node) -> Doc:
        return self.generic(node)

    def p_labeled_statement(self, node: Node) -> Doc:
        colon = node.first_of(":")
        if colon is None or node.children.index(colon) != 1 or len(node.children) != 3:
            return self.generic(node)
        return [self.print(node.children[0]), self.tok(colon), HARDLINE, self.print(node.children[2])]

    def p_local_declaration_statement(self, node: Node) -> Doc:
        parts: list[Doc] = []
        for i, child in enumerate(node.children):
            if i and child.text != ";":
                parts.append(" ")
            parts.append(self.print(child))
        return parts

    def p_global_statement(self, node: Node) -> Doc:
        return self.generic(node)

    def p_variable_declaration(self, node: Node) -> Doc:
        type_node = node.child("type")
        declarators = [c for c in node.children if c.type == "variable_declarator"]
        if type_node is None or not declarators:
            return self.generic(node)
        commas = [c for c in node.children if c.text == "," and not c.named]
        docs: list[Doc] = []
        for i, declarator in enumerate(declarators):
            doc = self.print(declarator)
            if i < len(commas):
                doc = [doc, self.tok(commas[i])]
            docs.append(doc)
        if len(docs) == 1:
            return [self.print(type_node), " ", docs[0]]
        return group([self.print(type_node), " ", docs[0], indent([[LINE, d] for d in docs[1:]])])

    def p_variable_declarator(self, node: Node) -> Doc:
        equals = node.first_of("=")
        if equals is None:
            return self.join_tokens([(c, self.print(c)) for c in node.children])
        index = node.children.index(equals)
        left = node.children[:index]
        value = node.children[index + 1 :]
        if len(value) != 1:
            return self.generic(node)
        return self.rhs(self.join_tokens([(c, self.print(c)) for c in left]), equals, value[0])

    # Assignment alignment -------------------------------------------------

    def aligned_assignments(self, items: Sequence[Node]) -> dict[int, Doc] | None:
        if not self.settings.align_assignments:
            return None
        return self.align_runs(items, self.assignment_split, self.statement_blank)

    def assignment_split(self, item: Node) -> tuple[Doc, Node, Node, Doc] | None:
        """(left, operator, value, end) for ``left = value;`` statements and fields."""
        node = item.children[0] if item.type == "global_statement" and item.children else item
        if node.verbatim:
            return None
        if node.type == "expression_statement" and len(node.children) == 2:
            assignment = node.children[0]
            if assignment.type != "assignment_expression":
                return None
            op = assignment.child("operator")
            left = assignment.child("left")
            value = assignment.child("right")
            if op is None or op.text != "=" or left is None or value is None:
                return None
            return (self.print(left), op, value, self.tok(node.children[1]))
        if node.type in ("local_declaration_statement", "field_declaration"):
            declaration = node.first_of("variable_declaration")
            if declaration is None or node.children[-1].text != ";":
                return None
            declarators = [c for c in declaration.children if c.type == "variable_declarator"]
            if len(declarators) != 1:
                return None
            declarator = declarators[0]
            equals = declarator.first_of("=")
            if equals is None:
                return None
            index = declarator.children.index(equals)
            values = declarator.children[index + 1 :]
            if len(values) != 1:
                return None
            type_node = declaration.child("type")
            if type_node is None:
                return None
            before = node.children[: node.children.index(declaration)]
            if any(c.type == "attribute_list" for c in before):
                return None
            left_parts: list[Doc] = [self.print(c) for c in before]
            left_parts.append(self.print(type_node))
            left_parts.append(self.join_tokens([(c, self.print(c)) for c in declarator.children[:index]]))
            return (join(" ", left_parts), equals, values[0], self.tok(node.children[-1]))
        return None

    def align_runs(
        self, items: Sequence[Node], splitter: Splitter, blank: Callable[[Node, Node], bool]
    ) -> dict[int, Doc] | None:
        """Pad the left sides of consecutive ``x = y`` items so the ``=`` line up.

        A run is items printed on consecutive lines (``blank`` is the list's
        own blank-line rule), each on one line. An item whose line would pass
        the width, aligned or not, is not aligned, so a run never makes a
        line break that formatting the output again would undo.
        """
        result: dict[int, Doc] = {}
        # (item, parts, left width, value width, indentation)
        run: list[tuple[Node, tuple[Doc, Node, Node, Doc], int, int, int]] = []
        above: dict[int, Doc] = {}

        def flush() -> None:
            if len(run) >= 2:
                target = max(entry[2] for entry in run)
                if all(depth + target + 3 + value + 1 <= self.settings.width for *_, value, depth in run):
                    for item, (left, op, value_node, end), width, _, _ in run:
                        padded = [left, " " * (target - width)]
                        result[id(item)] = [above.get(id(item), ""), self.rhs(padded, op, value_node), end]
            run.clear()

        kind = ""
        previous: Node | None = None
        for item in items:
            # A comment above an item prints before it; only the code aligns.
            comments, parts = self.split_leading(item, functools.partial(splitter, item))
            above[id(item)] = comments
            measured: tuple[int, int, int] | None = None
            if (
                parts is not None
                and not any(t.leading or t.trailing for t in _left_tokens(item))
                and not self.multiline_value(parts[2])
            ):
                width = self.flat_width(parts[0])
                value_width = self.flat_width(self.print(parts[2]))
                depth = self.indent_depth(item) * self.settings.indent_size
                if width is not None and value_width is not None and depth + width + 3 + value_width + 1 <= self.settings.width:
                    measured = (width, value_width, depth)
            item_kind = _kind(item)
            # A blank line, a comment or a different kind of item ends a run;
            # a comment above the first item of a run is fine.
            continues = (
                bool(run)
                and previous is run[-1][0]
                and not (blank(run[-1][0], item) or self.has_comments_before(item) or item_kind != kind)
            )
            if parts is None or measured is None or not continues:
                flush()
            if parts is not None and measured is not None:
                run.append((item, parts, *measured))
                kind = item_kind
            previous = item
        flush()
        return result or None


def _kind(item: Node) -> str:
    node = item.children[0] if item.type == "global_statement" and item.children else item
    return node.type


def _left_tokens(item: Node) -> list[Node]:
    """The tokens up to the first ``=``, other than the item's first token."""
    tokens: list[Node] = []
    for i, t in enumerate(item.tokens()):
        if t.text == "=":
            break
        if i:
            tokens.append(t)
    return tokens


def _starts_with_comment(node: Node) -> bool:
    first = node.first_token()
    return first is not None and bool(first.leading)


def _last_index(children: Sequence[Node], text: str) -> int | None:
    for i in range(len(children) - 1, -1, -1):
        if children[i].text == text and not children[i].named:
            return i
    return None


__all__ = ["BLOCK_STATEMENTS", "Statements", "SOFTLINE"]
