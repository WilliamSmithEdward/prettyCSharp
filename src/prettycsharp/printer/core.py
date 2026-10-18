"""The printer's shared machinery: dispatch, tokens, comments and lists.

Each syntax node type has a handler method named ``p_<type>`` in one of the
mixins (declarations, statements, expressions). A node without a handler is
printed by ``generic``, which joins its children with the spacing the source
had. Every token goes through ``tok``, which prints the comments attached to
it, so no comment is dropped by a handler that rearranges tokens.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from prettycsharp.doc import (
    BREAK_PARENT,
    ENSURE_LINE,
    HARDLINE,
    LINE,
    SOFTLINE,
    TRIM_INDENT,
    Doc,
    Group,
    IfBreak,
    LineSuffix,
    Wrapped,
    group,
    indent,
    join,
)
from prettycsharp.settings import Settings
from prettycsharp.syntax import DIRECTIVE_TYPES, Comment, Node, SourceFile

Handler = Callable[[Node], Doc]
T = TypeVar("T")

_WORD = re.compile(r"[A-Za-z0-9_@$\u0080-￿]")
# Operator characters that merge into a different token when written
# together, so printing them adjacent needs a space between.
_MERGING_PAIRS = {
    ("+", "+"),
    ("-", "-"),
    ("&", "&"),
    ("|", "|"),
    ("=", "="),
    ("<", "<"),
    (">", ">"),
    ("<", "="),
    (">", "="),
    ("!", "="),
    ("=", ">"),
    ("?", "?"),
    ("/", "/"),
    ("/", "*"),
    ("*", "/"),
    ("-", ">"),
    (":", ":"),
    (".", "."),
    ("+", "="),
    ("-", "="),
    ("*", "="),
    ("/", "="),
    ("%", "="),
    ("&", "="),
    ("|", "="),
    ("^", "="),
    ("?", "."),
    ("?", "["),
}

_URL = re.compile(r"\w+://")
_LIST_ITEM = re.compile(r"^(?:[-*+]\s|\d+[.)]\s)")

_INDENTING = frozenset(
    {"declaration_list", "block", "accessor_list", "enum_member_declaration_list"}
)

IGNORE = "prettycsharp-ignore"
IGNORE_START = "prettycsharp-ignore-start"
IGNORE_END = "prettycsharp-ignore-end"


def comment_body(comment: Comment) -> str:
    return comment.text[2:].strip()


class Core:
    def __init__(self, settings: Settings, file: SourceFile, lang_version: float) -> None:
        self.settings = settings
        self.file = file
        self.lang = lang_version
        self._blank_stack: list[Callable[[Node, Node], bool]] = []
        # Tokens whose leading comments were printed ahead of them.
        self._hoisted: set[int] = set()
        self._handlers: dict[str, Handler] = {}
        for name in dir(self):
            if name.startswith("p_"):
                self._handlers[name[2:]] = getattr(self, name)

    # Dispatch -----------------------------------------------------------

    def print(self, node: Node) -> Doc:
        if node.verbatim:
            return self.verbatim(node)
        if node.text is not None:
            return self.tok(node)
        handler = self._handlers.get(node.type)
        if handler is None:
            return self.generic(node)
        return handler(node)

    # Tokens and comments ------------------------------------------------

    def tok(self, t: Node | None, *, leading: bool = True, trailing: bool = True) -> Doc:
        if t is None:
            return ""
        if t.text is None:
            return self.print(t)
        parts: list[Doc] = []
        if leading and t.leading and id(t) not in self._hoisted:
            parts.append(self.leading_comments(t))
        parts.append(self.token_text(t))
        if trailing and t.trailing:
            parts.append(self.trailing_comments(t.trailing))
        return parts if len(parts) > 1 else parts[0]

    def token_text(self, t: Node) -> Doc:
        text = t.text or ""
        if "\n" in text or "\r" in text:
            return self.multiline_token(text)
        return text

    def multiline_token(self, text: str) -> Doc:
        # A multi-line string token is content: printed exactly, its line
        # breaks kept as written, its continuation lines not reindented.
        return [text, BREAK_PARENT]

    def hoist_leading(self, node: Node | None) -> Doc:
        """The comments before ``node``'s first token, printed now instead of with it."""
        if node is None or node.verbatim:
            return ""
        first = next(node.tokens(), None)
        if first is None or not first.leading or first.verbatim:
            return ""
        self._hoisted.add(id(first))
        return self.leading_comments(first)

    def leading_comments(self, t: Node, *, first_blank_allowed: bool = False) -> Doc:
        """The comments before a token, each on its own line, then the token's line."""
        # Each comment stood on its own line: start one if code is already on this line.
        parts: list[Doc] = [ENSURE_LINE]
        comments = t.leading
        i = 0
        while i < len(comments):
            comment = comments[i]
            if i > 0 or first_blank_allowed:
                if comment.newlines_before >= 2 and self.settings.max_blank_lines > 0:
                    parts.append(HARDLINE)
            # A run of line comments on consecutive lines is one block, so a
            # paragraph can be rewrapped as a whole.
            run = [comment]
            if comment.is_line and not comment.is_doc:
                while (
                    i + len(run) < len(comments)
                    and comments[i + len(run)].is_line
                    and not comments[i + len(run)].is_doc
                    and comments[i + len(run)].newlines_before == 1
                ):
                    run.append(comments[i + len(run)])
            if len(run) > 1 or comment.is_line:
                parts.append(self.line_comment_block(run))
                parts.append(HARDLINE)
            else:
                parts.append(self.block_comment(comment))
                parts.append(HARDLINE if comment.newline_after else " ")
            i += len(run)
        if t.newlines_before >= 2 and comments and self.settings.max_blank_lines > 0 and parts:
            if parts[-1] is HARDLINE:
                parts.append(HARDLINE)
        return parts

    def trailing_comments(self, comments: Sequence[Comment], *, break_parent: bool = True) -> Doc:
        """Comments after a token on its line.

        A line comment waits for the end of the line, and the printer puts
        any code after it on the next line. ``break_parent`` also breaks the
        enclosing groups, so a comment inside a list starts a layout of one
        item per line; a comment after a group's closing token does not need it.
        """
        parts: list[Doc] = []
        for comment in comments:
            if comment.is_line:
                parts.append(LineSuffix([" ", self.normalize_line_comment(comment.text)]))
                if break_parent:
                    parts.append(BREAK_PARENT)
            else:
                parts.append([" ", self.block_comment(comment)])
        return parts

    def normalize_line_comment(self, text: str) -> str:
        text = text.rstrip()
        if self.settings.comment_space and len(text) > 2 and text[2].isalnum():
            return "// " + text[2:]
        return text

    def block_comment(self, comment: Comment) -> Doc:
        lines = re.split(r"\r\n|\r|\n", comment.text)
        if len(lines) == 1:
            return comment.text
        rest = lines[1:]
        stars = all(line.strip().startswith("*") for line in rest if line.strip())
        if stars:
            body = [" " + line.strip() if line.strip() else "" for line in rest]
        else:
            margin = min((len(line) - len(line.lstrip()) for line in rest if line.strip()), default=0)
            body = [line[margin:].rstrip() for line in rest]
        parts: list[Doc] = [lines[0].rstrip()]
        for line in body:
            parts.append(HARDLINE)
            parts.append(line)
        return parts

    def line_comment_block(self, run: Sequence[Comment]) -> Doc:
        """Consecutive // comments: plain lines, with long paragraphs rewrapped."""
        texts = [self.normalize_line_comment(c.text) for c in run]
        if not self.settings.comment_wrap:
            return join(HARDLINE, texts)
        segments: list[Doc] = []
        paragraph: list[str] = []

        def flush() -> None:
            if paragraph:
                segments.append(_paragraph(list(paragraph)))
                paragraph.clear()

        for text in texts:
            if _reflowable(text, len(texts)):
                paragraph.append(text)
            else:
                flush()
                segments.append(text)
        flush()
        return join(HARDLINE, segments)

    # Verbatim ----------------------------------------------------------

    def verbatim(self, node: Node) -> Doc:
        first = node.first_token()
        last = node.last_token()
        if first is None or last is None or node.start < 0:
            return self.generic(node)
        text = self.file.text(first.start, last.end)
        parts: list[Doc] = []
        if first.leading:
            parts.append(self.leading_comments(first))
        if first.column == 0 and (first.text or "").startswith("#") and first.text not in ("#region", "#endregion"):
            # A directive written at column 0 stays there.
            parts.append(TRIM_INDENT)
        # Exactly as written, line breaks and trailing spaces included: they
        # may be inside a multi-line string.
        parts.append(self.multiline_token(text) if ("\n" in text or "\r" in text) else text)
        if last.trailing:
            parts.append(self.trailing_comments(last.trailing))
        return parts

    # Generic printing ---------------------------------------------------

    def generic(self, node: Node) -> Doc:
        """Children in order, separated by a space wherever the source had one."""
        parts: list[Doc] = []
        previous: Node | None = None
        for child in node.children:
            if previous is not None and self.space_between(previous, child):
                parts.append(" ")
            parts.append(self.print(child))
            previous = child
        return parts

    def space_between(self, left: Node, right: Node) -> bool:
        a = left.last_token()
        b = right.first_token()
        if a is None or b is None:
            return False
        if a.end >= 0 and b.start >= 0 and b.start >= a.end:
            if b.start > a.end or a.trailing or b.leading:
                return True
            return self.would_merge(a.text or "", b.text or "")
        return self.default_space(a.text or "", b.text or "")

    def default_space(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        if right in (",", ";", ")", "]", ".", "?.") or left in ("(", "[", ".", "?."):
            return False
        return True

    @staticmethod
    def would_merge(left: str, right: str) -> bool:
        if not left or not right:
            return False
        a, b = left[-1], right[0]
        if _WORD.match(a) and _WORD.match(b):
            return True
        return (a, b) in _MERGING_PAIRS

    def join_tokens(self, docs: Sequence[tuple[Node, Doc]]) -> Doc:
        """Docs for adjacent nodes, with a space only where tokens would merge."""
        parts: list[Doc] = []
        previous: Node | None = None
        for node, doc in docs:
            if previous is not None:
                a = previous.last_token()
                b = node.first_token()
                if a is not None and b is not None and self.would_merge(a.text or "", b.text or ""):
                    parts.append(" ")
            parts.append(doc)
            previous = node
        return parts

    def spaced(self, nodes: Iterable[Node]) -> Doc:
        """Nodes separated by single spaces."""
        return join(" ", [self.print(n) for n in nodes])

    def indent_depth(self, node: Node) -> int:
        """How many indentation levels the node will print at, as far as its ancestors tell."""
        depth = 0
        parent = node.parent
        while parent is not None:
            if parent.type in _INDENTING:
                depth += 1
            elif parent.type == "switch_section" or (parent.type == "switch_body" and self.settings.switch_case_indent):
                depth += 1
            parent = parent.parent
        return depth

    # Lists --------------------------------------------------------------

    def has_blank_before(self, node: Node) -> bool:
        first = node.first_token()
        if first is None or self.settings.max_blank_lines == 0:
            return False
        if first.leading:
            return first.leading[0].newlines_before >= 2
        return first.newlines_before >= 2

    def has_comments_before(self, node: Node) -> bool:
        first = node.first_token()
        return first is not None and bool(first.leading)

    def ignore_marker(self, node: Node) -> str | None:
        first = node.first_token()
        if first is None:
            return None
        for comment in first.leading:
            if comment.is_line and not comment.is_doc:
                body = comment_body(comment)
                if body in (IGNORE, IGNORE_START, IGNORE_END):
                    return body
        return None

    def is_column_zero_directive(self, node: Node) -> bool:
        """A directive written at column 0, or a verbatim item that starts with one."""
        first = node.first_token()
        if first is None or first.column != 0 or first.leading:
            return False
        if node.verbatim and node.type not in DIRECTIVE_TYPES:
            return (first.text or "").startswith("#") and first.text not in ("#region", "#endregion")
        return node.type in DIRECTIVE_TYPES and node.type not in ("preproc_region", "preproc_endregion")

    def print_list(
        self,
        items: Sequence[Node],
        blank: Callable[[Node, Node], bool],
        print_item: Callable[[Node], Doc] | None = None,
        aligned: dict[int, Doc] | None = None,
    ) -> Doc:
        """Items one per line; ``blank(previous, item)`` decides blank lines.

        Ignored regions are printed as written, and preprocessor directives
        take a line of their own.
        """
        printer = print_item or self.print
        if self.settings.regions == "remove":
            items = [i for i in items if i.type not in ("preproc_region", "preproc_endregion") or self.has_comments_before(i)]
        self._blank_stack.append(blank)
        try:
            return self._print_list(items, blank, printer, aligned)
        finally:
            self._blank_stack.pop()

    def _print_list(
        self,
        items: Sequence[Node],
        blank: Callable[[Node, Node], bool],
        printer: Callable[[Node], Doc],
        aligned: dict[int, Doc] | None,
    ) -> Doc:
        parts: list[Doc] = []
        previous: Node | None = None
        i = 0
        while i < len(items):
            item = items[i]
            marker = self.ignore_marker(item)
            if previous is not None:
                parts.append([HARDLINE, HARDLINE] if blank(previous, item) else HARDLINE)
            if self.is_column_zero_directive(item):
                # A directive written at column 0 stays there.
                parts.append(TRIM_INDENT)
            if marker == IGNORE_START:
                end = i
                while end + 1 < len(items) and self.ignore_marker(items[end + 1]) != IGNORE_END:
                    end += 1
                parts.append(self.verbatim_range(items[i : end + 1]))
                previous = items[end]
                i = end + 1
                continue
            if marker == IGNORE:
                parts.append(self.verbatim(item))
            elif aligned is not None and id(item) in aligned:
                parts.append(aligned[id(item)])
            else:
                parts.append(printer(item))
            previous = item
            i += 1
        return parts

    def verbatim_range(self, items: Sequence[Node]) -> Doc:
        first = items[0].first_token()
        last = items[-1].last_token()
        if first is None or last is None or first.start < 0 or last.end < 0:
            return join(HARDLINE, [self.print(item) for item in items])
        holder = Node(type="verbatim_range", start=first.start, end=last.end)
        holder.children = list(items)
        return self.verbatim(holder)

    # Shared layout helpers -----------------------------------------------

    def braced_list(self, open_tok: Node, items: Sequence[Doc], close_tok: Node, *, force_break: bool) -> Doc:
        """``{`` items ``}`` with each item on its own line when broken."""
        inner: list[Doc] = []
        if items:
            inner.append(indent([LINE, join([",", LINE], list(items))]))
        inner.append(self.close_comments(close_tok))
        inner.append(LINE)
        return group([self.tok(open_tok), inner, self.tok(close_tok, leading=False)], should_break=force_break)

    def split_leading(self, node: Node, build: Callable[[], T]) -> tuple[Doc, T]:
        """(the comments above the node, what ``build`` makes of the node without them)."""
        first = node.first_token()
        if first is None or not first.leading:
            return "", build()
        saved = first.leading
        first.leading = []
        try:
            built = build()
        finally:
            first.leading = saved
        return self.leading_comments(first), built

    def split_trailing(self, node: Node, build: Callable[[], T]) -> tuple[Doc, T]:
        """(the comments after the node's last token, what ``build`` makes of the node without them)."""
        last = node.last_token()
        if last is None or not last.trailing:
            return "", build()
        saved = last.trailing
        last.trailing = []
        try:
            built = build()
        finally:
            last.trailing = saved
        return self.trailing_comments(saved), built

    def closing(self, close: Node, line: Doc) -> Doc:
        """``line`` then the closing token, with comments before it on lines of their own first.

        With comments and no ``line`` (a closing token that hugs the last
        item), a line break still separates the last comment from the token.
        """
        if close.leading and line == "":
            line = HARDLINE
        return [
            self.close_comments(close),
            line,
            self.tok(close, leading=False, trailing=False),
            self.trailing_comments(close.trailing, break_parent=False),
        ]

    def close_comments(self, close: Node | None) -> Doc:
        """Comments before a closing token, printed inside the indented block."""
        if close is None or not close.leading:
            return ""
        parts = self.leading_comments(close)
        assert isinstance(parts, list)
        while parts and parts[-1] is HARDLINE:
            parts.pop()
        before: list[Doc] = [HARDLINE]
        if close.leading[0].newlines_before >= 2 and self.settings.max_blank_lines > 0:
            before.append(HARDLINE)
        return indent([*before, parts])

    def after_header(self, head_id: object | None) -> Doc:
        """What goes before an empty inline body: a space, or a line break when
        the header group ``head_id`` spans lines, as Visual Studio formats it."""
        if head_id is None:
            return " "
        return IfBreak(HARDLINE, " ", group_id=head_id)

    def open_brace(self, context: str) -> Doc:
        """What goes before an opening brace: a line break or a space."""
        style = self.settings.brace_style
        if style == "allman" or (style == "mixed" and context in ("type", "member", "namespace", "accessor")):
            return HARDLINE
        return " "

    def separated(self, node: Node, separator: str = ",") -> list[list[Node]]:
        """The children between the first and last token, split at separators."""
        return split(node.children[1:-1], separator)[0]

    def separators(self, node: Node, separator: str = ",") -> list[Node]:
        return split(node.children[1:-1], separator)[1]

    def current_blank(self) -> Callable[[Node, Node], bool]:
        """The blank-line rule of the list being printed, for directives inside it."""
        if self._blank_stack:
            return self._blank_stack[-1]
        return lambda previous, item: self.has_blank_before(item)


def split(nodes: Sequence[Node], separator: str = ",") -> tuple[list[list[Node]], list[Node]]:
    """Nodes split into items at separator tokens: (items, separators)."""
    items: list[list[Node]] = [[]]
    separators: list[Node] = []
    for node in nodes:
        if node.text == separator and not node.named:
            separators.append(node)
            items.append([])
        else:
            items[-1].append(node)
    if items[-1] == []:
        items.pop()
    return items, separators


def _paragraph(texts: list[str]) -> Doc:
    """Line comments printed as written unless one is too long, then rewrapped."""
    words = [word for text in texts for word in text[2:].split()]
    return Wrapped("// ", words, list(texts))


def _reflowable(text: str, run_length: int) -> bool:
    body = text[2:]
    stripped = body.strip()
    if not stripped or not body.startswith(" ") or body.startswith("  "):
        return False
    if stripped.endswith((";", "{", "}")) or "=>" in stripped:
        return False
    if _URL.search(stripped) or _LIST_ITEM.match(stripped):
        return False
    if stripped.upper().startswith("TODO") and run_length > 1:
        return False
    return True



__all__ = ["Core", "Group", "SOFTLINE", "comment_body"]
