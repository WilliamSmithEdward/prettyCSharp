"""Declarations: the file, namespaces, types, members, attributes and directives."""

from __future__ import annotations

from collections.abc import Sequence

from prettycsharp.doc import HARDLINE, LINE, SOFTLINE, TRIM_INDENT, Doc, group, indent, join
from prettycsharp.printer.core import split
from prettycsharp.printer.statements import Statements
from prettycsharp.rewrites import using_key
from prettycsharp.syntax import DIRECTIVE_TYPES, Node

TYPE_DECLARATIONS = frozenset(
    {
        "class_declaration",
        "struct_declaration",
        "interface_declaration",
        "record_declaration",
        "enum_declaration",
    }
)

MEMBER_DECLARATIONS = frozenset(
    {
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
        "delegate_declaration",
        "local_function_statement",
    }
)

# Children printed after the header: what follows a member's signature.
_TAIL_FIELDS = ("body", "accessors")
_NO_SPACE_BEFORE = frozenset(
    {"parameter_list", "bracketed_parameter_list", "type_parameter_list", "argument_list", "bracketed_argument_list"}
)


class Declarations(Statements):
    # The file -------------------------------------------------------------

    def p_compilation_unit(self, node: Node) -> Doc:
        items = node.children
        parts: list[Doc] = []
        if items:
            aligned = (
                self.align_runs(items, self.assignment_split, self.top_blank) if self.settings.align_assignments else None
            )
            parts.append(self.print_list(items, self.top_blank, aligned=aligned))
        trailing = self.file.trailing_comments
        if trailing:
            holder = Node(type="eof", text="")
            holder.leading = list(trailing)
            comments = self.leading_comments(holder, first_blank_allowed=False)
            assert isinstance(comments, list)
            while comments and comments[-1] is HARDLINE:
                comments.pop()
            if items:
                parts.append(HARDLINE)
                if trailing[0].newlines_before >= 2 and self.settings.max_blank_lines > 0:
                    parts.append(HARDLINE)
            parts.append(comments)
        return parts

    def top_blank(self, previous: Node, item: Node) -> bool:
        if previous.type == "file_scoped_namespace_declaration":
            return self.settings.max_blank_lines > 0
        if previous.type in DIRECTIVE_TYPES or item.type in DIRECTIVE_TYPES:
            return self.directive_blank(previous, item)
        if previous.type == item.type == "using_directive":
            return self.using_blank(previous, item)
        if previous.type == item.type and previous.type in ("extern_alias_directive", "global_attribute"):
            return False
        if previous.type == "global_statement" and item.type == "global_statement":
            return self.statement_blank(previous, item)
        return self.settings.max_blank_lines > 0

    def using_blank(self, previous: Node, item: Node) -> bool:
        """Usings stay together, except between groups when the order is grouped."""
        if self.settings.using_order != "system_first_grouped" or self.settings.max_blank_lines == 0:
            return False
        return _using_group(previous) != _using_group(item)

    def directive_blank(self, previous: Node, item: Node) -> bool:
        if self.settings.regions == "normalize":
            if previous.type == "preproc_region" or item.type == "preproc_endregion":
                return True
        return self.has_blank_before(item)

    # Directives -----------------------------------------------------------

    def p_preproc_if(self, node: Node) -> Doc:
        return self.conditional_directive(node)

    def p_preproc_elif(self, node: Node) -> Doc:
        return self.conditional_directive(node)

    def p_preproc_else(self, node: Node) -> Doc:
        return self.conditional_directive(node)

    def conditional_directive(self, node: Node) -> Doc:
        children = node.children
        if not children:
            return self.generic(node)
        condition = node.child("condition")
        header_end = children.index(condition) if condition is not None else 0
        header = self.verbatim_range(children[: header_end + 1])
        blank = self.current_blank()
        parts: list[Doc] = [header]
        # In source order: runs of items, the next branch, and #endif.
        run: list[Node] = []

        def flush() -> None:
            if run:
                parts.append(self.directive_line(run[0]))
                parts.append(self.print_list(list(run), blank))
                run.clear()

        for child in children[header_end + 1 :]:
            if child.field == "alternative" or child.text == "#endif":
                flush()
                parts.append(self.directive_line(child))
                parts.append(self.print(child) if child.text is None else self.verbatim_range([child]))
            else:
                run.append(child)
        flush()
        return parts

    def directive_line(self, node: Node) -> Doc:
        """The line break before a directive line or the first item after one."""
        # A directive written at column 0 stays there; #endif is a bare token.
        at_zero = self.is_column_zero_directive(node) or (
            node.text is not None and node.text.startswith("#") and node.column == 0 and not node.leading
        )
        line: Doc = HARDLINE
        if self.has_blank_before(node):
            line = [HARDLINE, HARDLINE]
        return [line, TRIM_INDENT] if at_zero else line

    def p_preproc_region(self, node: Node) -> Doc:
        return self.verbatim(node)

    def p_preproc_endregion(self, node: Node) -> Doc:
        return self.verbatim(node)

    def p_shebang_directive(self, node: Node) -> Doc:
        return self.verbatim(node)

    def generic_directive(self, node: Node) -> Doc:
        return self.verbatim(node)

    p_preproc_define = generic_directive
    p_preproc_undef = generic_directive
    p_preproc_pragma = generic_directive
    p_preproc_nullable = generic_directive
    p_preproc_error = generic_directive
    p_preproc_warning = generic_directive
    p_preproc_line = generic_directive
    p_preproc_if_in_attribute_list = generic_directive

    # Usings and namespaces --------------------------------------------------

    def p_using_directive(self, node: Node) -> Doc:
        return self.words(node.children)

    def p_extern_alias_directive(self, node: Node) -> Doc:
        return self.words(node.children)

    def words(self, nodes: Sequence[Node]) -> Doc:
        """Nodes separated by spaces, with none before ``;``."""
        parts: list[Doc] = []
        for i, child in enumerate(nodes):
            if i and child.text != ";":
                parts.append(" ")
            parts.append(self.print(child))
        return parts

    def p_namespace_declaration(self, node: Node) -> Doc:
        body = node.child("body")
        if body is None or body.type != "declaration_list":
            return self.generic(node)
        index = node.children.index(body)
        return [self.words(node.children[:index]), self.declaration_body(body, "namespace"), self.words(node.children[index + 1 :])]

    def p_file_scoped_namespace_declaration(self, node: Node) -> Doc:
        return self.words(node.children)

    def declaration_body(self, body: Node, context: str) -> Doc:
        if len(body.children) < 2 or body.verbatim:
            return [" ", self.print(body)]
        open_tok = body.children[0]
        close_tok = body.children[-1]
        items = body.children[1:-1]
        if not items and not close_tok.leading and not open_tok.trailing:
            if self.settings.empty_bodies == "inline":
                return [" ", self.tok(open_tok), " ", self.tok(close_tok)]
            return [self.open_brace(context), self.tok(open_tok), HARDLINE, self.tok(close_tok)]
        inner: Doc = ""
        if items:
            inner = indent([HARDLINE, self.members(items)])
        return [
            self.open_brace(context),
            self.tok(open_tok),
            inner,
            self.close_comments(close_tok),
            HARDLINE,
            self.tok(close_tok, leading=False),
        ]

    def members(self, items: Sequence[Node]) -> Doc:
        aligned = (
            self.align_runs(items, self.assignment_split, self.member_blank) if self.settings.align_assignments else None
        )
        return self.print_list(items, self.member_blank, aligned=aligned)

    def member_blank(self, previous: Node, item: Node) -> bool:
        if previous.type in DIRECTIVE_TYPES or item.type in DIRECTIVE_TYPES:
            return self.directive_blank(previous, item)
        if self.settings.max_blank_lines == 0:
            return False
        mode = self.settings.member_blank_lines
        if mode == "preserve":
            return self.has_blank_before(item)
        if mode == "all":
            return True
        if previous.type == item.type == "using_directive":
            return self.using_blank(previous, item)
        if previous.type == item.type == "extern_alias_directive":
            return False
        if (
            self.is_tight(previous)
            and self.is_tight(item)
            and previous.type == item.type
            and not self.has_comments_before(item)
        ):
            return False
        return True

    def is_tight(self, node: Node) -> bool:
        if node.type in ("field_declaration", "event_field_declaration"):
            return True
        if node.type == "property_declaration":
            accessors = node.child("accessors")
            if accessors is None:
                return True
            return all(a.child("body") is None for a in accessors.children if a.type == "accessor_declaration")
        return False

    # Types ------------------------------------------------------------------

    def type_declaration(self, node: Node) -> Doc:
        body = node.child("body")
        if body is None:
            body = node.first_of("declaration_list", "enum_member_declaration_list")
        attributes, header, constraints, tail = self.split_declaration(node, body)
        parts: list[Doc] = [self.attribute_lines(attributes), self.header(header)]
        if constraints:
            parts.append(self.constraints(constraints))
        if body is not None:
            if body.type == "enum_member_declaration_list":
                parts.append(self.enum_body(body))
            else:
                parts.append(self.declaration_body(body, "type"))
        parts.append(self.words(tail) if tail else "")
        return parts

    p_class_declaration = type_declaration
    p_struct_declaration = type_declaration
    p_interface_declaration = type_declaration
    p_record_declaration = type_declaration
    p_enum_declaration = type_declaration

    def split_declaration(
        self, node: Node, body: Node | None
    ) -> tuple[list[Node], list[Node], list[Node], list[Node]]:
        """(attribute lists, header, constraint clauses, what follows the body)."""
        attributes: list[Node] = []
        header: list[Node] = []
        constraints: list[Node] = []
        tail: list[Node] = []
        seen_body = False
        for child in node.children:
            if child is body:
                seen_body = True
            elif seen_body:
                tail.append(child)
            elif child.type == "attribute_list" and not header:
                attributes.append(child)
            elif child.type == "type_parameter_constraints_clause":
                constraints.append(child)
            else:
                header.append(child)
        return attributes, header, constraints, tail

    def attribute_lines(self, attributes: Sequence[Node]) -> Doc:
        return [[self.print(a), HARDLINE] for a in attributes]

    def header(self, nodes: Sequence[Node]) -> Doc:
        parts: list[Doc] = []
        previous: Node | None = None
        for child in nodes:
            if previous is not None and self.header_space(previous, child):
                parts.append(" ")
            parts.append(self.print(child))
            previous = child
        return parts

    def header_space(self, previous: Node, child: Node) -> bool:
        if child.type in _NO_SPACE_BEFORE:
            return False
        if previous.text == "~" or previous.type == "explicit_interface_specifier":
            return False
        if child.text == ";":
            return False
        return True

    def constraints(self, clauses: Sequence[Node]) -> Doc:
        return group(indent([[LINE, self.print(c)] for c in clauses]))

    def p_base_list(self, node: Node) -> Doc:
        if not node.children or node.children[0].text != ":":
            return self.generic(node)
        colon = node.children[0]
        items, commas = split(node.children[1:])
        docs: list[Doc] = []
        for i, item in enumerate(items):
            doc = self.join_tokens([(c, self.print(c)) for c in item])
            if i < len(commas):
                doc = [doc, self.tok(commas[i])]
            docs.append(doc)
        return group([self.tok(colon), indent([LINE, join(LINE, docs)])]) if len(docs) > 1 else [self.tok(colon), " ", docs[0] if docs else ""]

    def p_primary_constructor_base_type(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    def p_type_parameter_constraints_clause(self, node: Node) -> Doc:
        colon = node.first_of(":")
        if colon is None:
            return self.generic(node)
        index = node.children.index(colon)
        items, commas = split(node.children[index + 1 :])
        docs: list[Doc] = []
        for i, item in enumerate(items):
            doc = self.generic_sequence(item)
            if i < len(commas):
                doc = [doc, self.tok(commas[i])]
            docs.append(doc)
        return [self.words(node.children[:index]), " ", self.tok(colon), " ", join(" ", docs)]

    def p_type_parameter_constraint(self, node: Node) -> Doc:
        return self.generic_sequence(node.children)

    def p_constructor_constraint(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])

    # Enums ----------------------------------------------------------------

    def enum_body(self, body: Node) -> Doc:
        if len(body.children) < 2 or any(c.type in DIRECTIVE_TYPES for c in body.children):
            return [" ", self.verbatim(body)]
        open_tok = body.children[0]
        close_tok = body.children[-1]
        items, commas = self.items_and_commas(body)
        if not items and not close_tok.leading:
            if self.settings.empty_bodies == "inline":
                return [" ", self.tok(open_tok), " ", self.tok(close_tok)]
            return [self.open_brace("type"), self.tok(open_tok), HARDLINE, self.tok(close_tok)]
        members = [item[0] for item in items if len(item) == 1]
        if len(members) != len(items):
            return [" ", self.verbatim(body)]
        aligned: dict[int, Doc] = {}
        if self.settings.align_enum_values:
            aligned = self.align_runs(members, self.enum_split, lambda a, b: self.has_blank_before(b)) or {}
        docs: list[Doc] = []
        for i, member in enumerate(members):
            doc = aligned.get(id(member)) or self.print(member)
            if i < len(commas):
                keep = i < len(members) - 1 or self.settings.trailing_commas != "remove"
                if keep:
                    doc = [doc, self.tok(commas[i])]
            elif i < len(members) - 1:
                doc = [doc, ","]
            elif self.settings.trailing_commas == "add":
                doc = [doc, ","]
            docs.append(doc)
        lines: list[Doc] = []
        for i, (member, doc) in enumerate(zip(members, docs, strict=True)):
            if i:
                lines.append([HARDLINE, HARDLINE] if self.has_blank_before(member) else HARDLINE)
            lines.append(doc)
        return [
            self.open_brace("type"),
            self.tok(open_tok),
            indent([HARDLINE, lines]) if lines else "",
            self.close_comments(close_tok),
            HARDLINE,
            self.tok(close_tok, leading=False),
        ]

    def enum_split(self, member: Node) -> tuple[Doc, Node, Node, Doc] | None:
        equals = member.first_of("=")
        value = member.child("value")
        name = member.child("name")
        if equals is None or value is None or name is None or member.first_of("attribute_list") is not None:
            return None
        return (self.print(name), equals, value, "")

    def p_enum_member_declaration(self, node: Node) -> Doc:
        attributes = [c for c in node.children if c.type == "attribute_list"]
        rest = [c for c in node.children if c.type != "attribute_list"]
        equals = next((c for c in rest if c.text == "="), None)
        if equals is not None and len(rest) == 3 and rest[1] is equals:
            return [self.attribute_lines(attributes), self.rhs(self.print(rest[0]), equals, rest[2])]
        return [self.attribute_lines(attributes), self.words(rest)]

    # Members ----------------------------------------------------------------

    def member(self, node: Node) -> Doc:
        body = node.child("body")
        accessors = node.child("accessors")
        arrow_value = node.child("value") if node.type in ("property_declaration", "indexer_declaration") else None
        initializer_start = None
        if node.type == "property_declaration" and accessors is not None:
            equals = next((c for c in node.children if c.text == "=" and not c.named), None)
            if equals is not None:
                initializer_start = node.children.index(equals)
        attributes: list[Node] = []
        header: list[Node] = []
        constraints: list[Node] = []
        ctor_init: Node | None = None
        tail_start = len(node.children)
        for i, child in enumerate(node.children):
            if child is body or child is accessors or (arrow_value is not None and child is arrow_value and child.type == "arrow_expression_clause"):
                tail_start = i
                break
            if child.type == "attribute_list" and not header:
                attributes.append(child)
            elif child.type == "type_parameter_constraints_clause":
                constraints.append(child)
            elif child.type == "constructor_initializer":
                ctor_init = child
            elif child.text == ";" and i == len(node.children) - 1:
                tail_start = i
                break
            else:
                header.append(child)
        parts: list[Doc] = [self.attribute_lines(attributes), self.header(header)]
        if ctor_init is not None:
            parts.append(group(indent([LINE, self.print(ctor_init)])))
        if constraints:
            parts.append(self.constraints(constraints))
        rest = node.children[tail_start:]
        i = 0
        while i < len(rest):
            child = rest[i]
            if child is body and child.type == "block":
                parts.append(self.block(child, "member"))
            elif child.type == "arrow_expression_clause":
                parts.append(self.expression_body(child))
            elif child is accessors:
                parts.append(self.accessor_list(child))
            elif initializer_start is not None and child is node.children[initializer_start]:
                value = rest[i + 1] if i + 1 < len(rest) else None
                if value is not None and value.text != ";":
                    parts.append(self.rhs("", child, value))
                    i += 2
                    continue
                parts.append([" ", self.tok(child)])
            elif child.text == ";":
                parts.append(self.tok(child))
            else:
                parts.append([" ", self.print(child)])
            i += 1
        return parts

    p_method_declaration = member
    p_constructor_declaration = member
    p_destructor_declaration = member
    p_operator_declaration = member
    p_conversion_operator_declaration = member
    p_property_declaration = member
    p_indexer_declaration = member
    p_event_declaration = member
    p_delegate_declaration = member
    p_local_function_statement = member

    def p_field_declaration(self, node: Node) -> Doc:
        attributes = [c for c in node.children if c.type == "attribute_list"]
        rest = [c for c in node.children if c.type != "attribute_list"]
        return [self.attribute_lines(attributes), self.words(rest)]

    p_event_field_declaration = p_field_declaration

    def p_constructor_initializer(self, node: Node) -> Doc:
        if not node.children or node.children[0].text != ":":
            return self.generic(node)
        rest = node.children[1:]
        return [self.tok(node.children[0]), " ", self.join_tokens([(c, self.print(c)) for c in rest])]

    def accessor_list(self, node: Node) -> Doc:
        if len(node.children) < 2 or node.verbatim:
            return [" ", self.print(node)]
        open_tok = node.children[0]
        close_tok = node.children[-1]
        accessors = node.children[1:-1]
        simple = all(
            a.type == "accessor_declaration"
            and a.child("body") is None
            and a.first_of("attribute_list") is None
            and not any(t.leading or t.trailing for t in a.tokens())
            for a in accessors
        ) and not close_tok.leading and not open_tok.trailing
        if simple and accessors:
            return [" ", self.tok(open_tok), " ", join(" ", [self.print(a) for a in accessors]), " ", self.tok(close_tok)]
        if not accessors and not close_tok.leading:
            return [" ", self.tok(open_tok), " ", self.tok(close_tok)]
        body: Doc = ""
        if accessors:
            body = indent([HARDLINE, self.print_list(accessors, lambda a, b: self.has_blank_before(b))])
        return [
            self.open_brace("accessor"),
            self.tok(open_tok),
            body,
            self.close_comments(close_tok),
            HARDLINE,
            self.tok(close_tok, leading=False),
        ]

    def p_accessor_list(self, node: Node) -> Doc:
        return self.accessor_list(node)

    def p_accessor_declaration(self, node: Node) -> Doc:
        body = node.child("body")
        attributes = [c for c in node.children if c.type == "attribute_list"]
        header: list[Node] = []
        rest: list[Node] = []
        for child in node.children:
            if child.type == "attribute_list":
                continue
            if child is body or rest or child.text == ";":
                rest.append(child)
            else:
                header.append(child)
        parts: list[Doc] = [self.attribute_lines(attributes), self.words(header)]
        for child in rest:
            if child is body and child.type == "block":
                parts.append(self.block(child, "accessor"))
            elif child.type == "arrow_expression_clause":
                parts.append(self.expression_body(child))
            else:
                parts.append(self.tok(child))
        return parts

    def p_arrow_expression_clause(self, node: Node) -> Doc:
        return self.expression_body(node)

    # Parameters ------------------------------------------------------------

    def p_parameter_list(self, node: Node) -> Doc:
        return self.parameters(node)

    def p_bracketed_parameter_list(self, node: Node) -> Doc:
        return self.parameters(node)

    def parameters(self, node: Node) -> Doc:
        if len(node.children) < 2 or node.children[0].text not in ("(", "["):
            return self.generic(node)
        open_tok = node.children[0]
        close_tok = node.children[-1]
        items, commas = self.items_and_commas(node)
        if not items:
            return [self.tok(open_tok), self.close_comments(close_tok), self.tok(close_tok, leading=False)]
        docs: list[Doc] = []
        for i, item in enumerate(items):
            doc = self.parameter_item(item)
            if i < len(commas):
                doc = [doc, self.tok(commas[i])]
            docs.append(doc)
        style = self.settings.argument_wrap
        if style == "one_per_line" or style not in ("one_per_line_close_on_last", "fill", "align"):
            return group([self.tok(open_tok), indent([SOFTLINE, join(LINE, docs)]), SOFTLINE, self.close_comments(close_tok), self.tok(close_tok, leading=False)])
        return self.argument_layout(open_tok, docs, close_tok, [])

    def parameter_item(self, item: Sequence[Node]) -> Doc:
        if len(item) == 1:
            return self.print(item[0])
        # A params parameter is not wrapped in a node: params int[] values.
        return self.words(item)

    def p_parameter(self, node: Node) -> Doc:
        return self.words(node.children)

    def p_implicit_parameter(self, node: Node) -> Doc:
        return self.generic(node)

    # Attributes -------------------------------------------------------------

    def p_attribute_list(self, node: Node) -> Doc:
        parts: list[Doc] = []
        for child in node.children:
            parts.append(self.print(child))
            if child.text in (",", ":") and not child.named or child.type == "attribute_target_specifier":
                parts.append(" ")
        return parts

    p_global_attribute = p_attribute_list

    def p_attribute_target_specifier(self, node: Node) -> Doc:
        return [self.print(c) for c in node.children]

    def p_attribute(self, node: Node) -> Doc:
        return self.join_tokens([(c, self.print(c)) for c in node.children])


def _using_group(node: Node) -> tuple[int, int, str]:
    """global or not, plain, static or alias, and the first part of the name."""
    is_global, kind, _, name = using_key(node, "system_first_grouped")
    return (is_global, kind, name.split(".")[0])
