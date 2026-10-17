"""The layout document model and the printer that fits it to a line width.

A document describes text with optional line breaks, in the style of
Wadler's "prettier printer" as Prettier implements it. A ``Group`` prints on
one line when it fits and breaks every ``Line`` directly inside it when it
does not. ``HARDLINE`` always breaks and forces every enclosing group to
break. The printer is iterative, so deeply nested documents do not exhaust
the Python stack.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

# A document is a str, a list of documents, or one of the node classes below.
Doc = object

_MODE_BREAK = 0
_MODE_FLAT = 1


@dataclass(eq=False, slots=True)
class Group:
    contents: Doc
    should_break: bool = False
    id: object | None = None
    # A conditional group: the printer uses the first state that fits, and
    # the last one when none does.
    expanded_states: Sequence[Doc] | None = None


@dataclass(eq=False, slots=True)
class Indent:
    contents: Doc


@dataclass(eq=False, slots=True)
class Align:
    """Indent the contents by ``spaces`` extra columns."""

    spaces: int
    contents: Doc


@dataclass(eq=False, slots=True)
class Line:
    hard: bool = False
    soft: bool = False
    literal: bool = False


@dataclass(eq=False, slots=True)
class IfBreak:
    break_contents: Doc
    flat_contents: Doc = ""
    group_id: object | None = None


@dataclass(eq=False, slots=True)
class IndentIfBreak:
    contents: Doc
    group_id: object


@dataclass(eq=False, slots=True)
class LineSuffix:
    """Text deferred to the end of the line, such as a trailing comment."""

    contents: Doc


@dataclass(eq=False, slots=True)
class BreakParent:
    pass


@dataclass(eq=False, slots=True)
class EnsureLine:
    """A line break, unless nothing but indentation is on the line yet.

    Comments that stood on lines of their own come after one, so they never
    end up behind code, where the next formatting would take them for
    trailing comments.
    """


@dataclass(eq=False, slots=True)
class Fill:
    """Content, separator, content, ...: separators break only where needed."""

    parts: list[Doc] = field(default_factory=list)


@dataclass(eq=False, slots=True)
class Wrapped:
    """Words that wrap to the line width at print time, each line prefixed.

    Used for comment paragraphs: ``prefix`` is ``"// "`` and the words are
    laid out greedily, so the result depends on the indentation the printer
    reaches, which is known only while printing.
    """

    prefix: str
    words: list[str]
    # The lines as written. When given, they are printed unchanged unless
    # one of them would pass the line width; only then are the words wrapped.
    lines: list[str] | None = None


@dataclass(eq=False, slots=True)
class TrimIndent:
    """Remove the indentation printed since the last line break: go to column 0."""


LINE = Line()
SOFTLINE = Line(soft=True)
ENSURE_LINE = EnsureLine()
TRIM_INDENT = TrimIndent()
_HARD = Line(hard=True)
_BREAK_PARENT = BreakParent()
HARDLINE: Doc = [_HARD, _BREAK_PARENT]
LITERALLINE: Doc = [Line(hard=True, literal=True), _BREAK_PARENT]
BREAK_PARENT = _BREAK_PARENT


def group(contents: Doc, should_break: bool = False, id: object | None = None) -> Group:
    return Group(contents, should_break, id)


def conditional_group(states: Sequence[Doc]) -> Group:
    return Group(states[0], False, None, list(states))


def indent(contents: Doc) -> Indent:
    return Indent(contents)


def join(separator: Doc, docs: Sequence[Doc]) -> list[Doc]:
    out: list[Doc] = []
    for i, doc in enumerate(docs):
        if i:
            out.append(separator)
        out.append(doc)
    return out


def propagate_breaks(doc: Doc) -> None:
    """Mark every group that contains a hard break as broken.

    A conditional group stops the propagation, as in Prettier: its states
    decide for themselves how much of them may break.
    """
    # Each stack entry is (doc, exiting). Groups are tracked in group_stack.
    group_stack: list[Group] = []
    stack: list[tuple[Doc, bool]] = [(doc, False)]
    seen: set[int] = set()
    while stack:
        node, exiting = stack.pop()
        if exiting:
            assert isinstance(node, Group)
            group_stack.pop()
            if node.should_break and group_stack:
                _break_parent(group_stack)
            continue
        if isinstance(node, str):
            continue
        if isinstance(node, list):
            for child in reversed(node):
                stack.append((child, False))
        elif isinstance(node, BreakParent):
            if group_stack:
                _break_parent(group_stack)
        elif isinstance(node, Group):
            if id(node) in seen:
                # A group shared between conditional states: its own break
                # flag is already settled; still tell the parent.
                if node.should_break and group_stack:
                    _break_parent(group_stack)
                continue
            seen.add(id(node))
            group_stack.append(node)
            stack.append((node, True))
            if node.expanded_states is not None:
                for state in reversed(node.expanded_states):
                    stack.append((state, False))
            else:
                stack.append((node.contents, False))
        elif isinstance(node, (Indent, Align, LineSuffix, IndentIfBreak)):
            stack.append((node.contents, False))
        elif isinstance(node, IfBreak):
            stack.append((node.flat_contents, False))
            stack.append((node.break_contents, False))
        elif isinstance(node, Fill):
            for child in reversed(node.parts):
                stack.append((child, False))


def _break_parent(group_stack: list[Group]) -> None:
    parent = group_stack[-1]
    if parent.expanded_states is None and not parent.should_break:
        parent.should_break = True


@dataclass(slots=True)
class _Indentation:
    text: str
    width: int


class Printer:
    def __init__(self, width: int, indent_unit: str, indent_width: int, eol: str) -> None:
        self.width = width
        self.indent_unit = indent_unit
        self.indent_width = indent_width
        self.eol = eol
        self._indent_cache: dict[tuple[int, int], _Indentation] = {}

    def _indentation(self, base: _Indentation, *, levels: int = 0, spaces: int = 0) -> _Indentation:
        return _Indentation(
            base.text + self.indent_unit * levels + " " * spaces,
            base.width + self.indent_width * levels + spaces,
        )

    def print(self, doc: Doc) -> str:
        propagate_breaks(doc)
        root = _Indentation("", 0)
        out: list[str] = []
        pos = 0
        line_suffix: list[tuple[_Indentation, int, Doc]] = []
        group_modes: dict[object, int] = {}
        cmds: list[tuple[_Indentation, int, Doc]] = [(root, _MODE_BREAK, doc)]
        # Whether anything but whitespace is on the current line yet.
        content = False

        while cmds:
            ind, mode, node = cmds.pop()
            if isinstance(node, str):
                if line_suffix and node.strip():
                    # Code after an end-of-line comment goes on the next line,
                    # so the comment stays behind the code it followed.
                    cmds.append((ind, mode, node))
                    cmds.append((ind, mode, _HARD))
                    continue
                out.append(node)
                newline = node.rfind("\n")
                if newline >= 0:
                    pos = len(node) - newline - 1
                    content = bool(node[newline + 1 :].strip())
                else:
                    pos += len(node)
                    content = content or bool(node.strip())
            elif isinstance(node, TrimIndent):
                if not content:
                    _trim(out)
                    pos = 0
            elif isinstance(node, EnsureLine):
                if content:
                    cmds.append((ind, mode, _HARD))
                elif line_suffix:
                    # End-of-line comments with no code left on their line:
                    # each takes a line of its own, at this indentation.
                    _trim(out)
                    if out and out[-1].endswith(("\n", "\r")):
                        out.append(ind.text)
                        pos = ind.width
                    for _, suffix_mode, suffix in reversed(line_suffix):
                        cmds.append((ind, suffix_mode, _HARD))
                        cmds.append((ind, suffix_mode, _without_leading_space(suffix)))
                    line_suffix = []
                elif out:
                    # Only spaces since the line break: start at this indentation.
                    _trim(out)
                    if out and out[-1].endswith(("\n", "\r")):
                        out.append(ind.text)
                        pos = ind.width
            elif isinstance(node, list):
                for child in reversed(node):
                    cmds.append((ind, mode, child))
            elif isinstance(node, Indent):
                cmds.append((self._indentation(ind, levels=1), mode, node.contents))
            elif isinstance(node, Align):
                # A negative width aligns to the column the printer is at.
                spaces = node.spaces if node.spaces >= 0 else max(pos - ind.width, 0)
                cmds.append((self._indentation(ind, spaces=spaces), mode, node.contents))
            elif isinstance(node, Group):
                if mode == _MODE_FLAT and not node.should_break:
                    cmds.append((ind, _MODE_FLAT, node.contents))
                    if node.id is not None:
                        group_modes[node.id] = _MODE_FLAT
                    continue
                flat = (ind, _MODE_FLAT, node.contents)
                rem = self.width - pos
                if not node.should_break and self._fits(flat, cmds, rem, group_modes):
                    cmds.append(flat)
                    chosen = _MODE_FLAT
                elif node.expanded_states is not None:
                    most_expanded = node.expanded_states[-1]
                    if node.should_break:
                        cmds.append((ind, _MODE_BREAK, most_expanded))
                        chosen = _MODE_BREAK
                    else:
                        chosen = _MODE_BREAK
                        for state in node.expanded_states[1:]:
                            attempt = (ind, _MODE_FLAT, state)
                            if self._fits(attempt, cmds, rem, group_modes):
                                cmds.append(attempt)
                                chosen = _MODE_FLAT
                                break
                        else:
                            cmds.append((ind, _MODE_BREAK, most_expanded))
                else:
                    cmds.append((ind, _MODE_BREAK, node.contents))
                    chosen = _MODE_BREAK
                if node.id is not None:
                    group_modes[node.id] = chosen
            elif isinstance(node, Fill):
                self._print_fill(ind, mode, node, cmds, pos, line_suffix, group_modes)
            elif isinstance(node, IfBreak):
                group_mode = group_modes.get(node.group_id, _MODE_FLAT) if node.group_id is not None else mode
                contents = node.break_contents if group_mode == _MODE_BREAK else node.flat_contents
                cmds.append((ind, mode, contents))
            elif isinstance(node, IndentIfBreak):
                group_mode = group_modes.get(node.group_id, _MODE_FLAT)
                if group_mode == _MODE_BREAK:
                    cmds.append((self._indentation(ind, levels=1), mode, node.contents))
                else:
                    cmds.append((ind, mode, node.contents))
            elif isinstance(node, LineSuffix):
                if line_suffix:
                    # Two end-of-line comments cannot share a line: the first
                    # would swallow the second. Break the line between them.
                    cmds.append((ind, mode, node))
                    cmds.append((ind, mode, _HARD))
                    continue
                line_suffix.append((ind, mode, node.contents))
            elif isinstance(node, BreakParent):
                pass
            elif isinstance(node, Wrapped):
                pos = self._print_wrapped(ind, node, out, pos)
                content = True
            elif isinstance(node, Line):
                if mode == _MODE_FLAT and not node.hard:
                    if not node.soft:
                        out.append(" ")
                        pos += 1
                    continue
                if line_suffix:
                    cmds.append((ind, mode, node))
                    for entry in reversed(line_suffix):
                        cmds.append(entry)
                    line_suffix = []
                    # The comment brings its own space.
                    _trim(out)
                    continue
                _trim(out)
                content = False
                if node.literal:
                    out.append(self.eol)
                    pos = 0
                else:
                    out.append(self.eol + ind.text)
                    pos = ind.width
            else:  # pragma: no cover - a programming error
                raise TypeError(f"not a document: {node!r}")

            if not cmds and line_suffix:
                for entry in reversed(line_suffix):
                    cmds.append(entry)
                line_suffix = []
        _trim(out)
        return "".join(out)

    def _fits(
        self,
        next_cmd: tuple[_Indentation, int, Doc],
        rest: list[tuple[_Indentation, int, Doc]],
        width: int,
        group_modes: dict[object, int],
        must_be_flat: bool = False,
    ) -> bool:
        rest_index = len(rest)
        cmds: list[tuple[int, Doc]] = [(next_cmd[1], next_cmd[2])]
        while width >= 0:
            if not cmds:
                if rest_index == 0:
                    return True
                rest_index -= 1
                entry = rest[rest_index]
                cmds.append((entry[1], entry[2]))
                continue
            mode, node = cmds.pop()
            if isinstance(node, str):
                newline = node.find("\n")
                if newline >= 0:
                    # A multi-line token: only its first line has to fit.
                    return width - newline >= 0
                width -= len(node)
            elif isinstance(node, list):
                for child in reversed(node):
                    cmds.append((mode, child))
            elif isinstance(node, Fill):
                for child in reversed(node.parts):
                    cmds.append((mode, child))
            elif isinstance(node, LineSuffix):
                # Printed at the end of the line, so it takes no width here.
                continue
            elif isinstance(node, (Indent, Align, IndentIfBreak)):
                cmds.append((mode, node.contents))
            elif isinstance(node, Group):
                if must_be_flat and node.should_break:
                    return False
                group_mode = _MODE_BREAK if node.should_break else mode
                contents = node.contents
                if node.expanded_states is not None and group_mode == _MODE_BREAK:
                    contents = node.expanded_states[-1]
                cmds.append((group_mode, contents))
            elif isinstance(node, IfBreak):
                group_mode = group_modes.get(node.group_id, _MODE_FLAT) if node.group_id is not None else mode
                contents = node.break_contents if group_mode == _MODE_BREAK else node.flat_contents
                cmds.append((mode, contents))
            elif isinstance(node, Line):
                if mode == _MODE_BREAK or node.hard:
                    return True
                if not node.soft:
                    width -= 1
            elif isinstance(node, (Wrapped, EnsureLine)):
                return True
        return False

    def _print_fill(
        self,
        ind: _Indentation,
        mode: int,
        node: Fill,
        cmds: list[tuple[_Indentation, int, Doc]],
        pos: int,
        line_suffix: list[tuple[_Indentation, int, Doc]],
        group_modes: dict[object, int],
    ) -> None:
        parts = node.parts
        if not parts:
            return
        rem = self.width - pos
        content = parts[0]
        content_flat = (ind, _MODE_FLAT, content)
        content_fits = self._fits(content_flat, [], rem, group_modes, True)
        if len(parts) == 1:
            cmds.append(content_flat if content_fits else (ind, _MODE_BREAK, content))
            return
        whitespace = parts[1]
        if len(parts) == 2:
            if content_fits:
                cmds.append((ind, _MODE_FLAT, whitespace))
                cmds.append(content_flat)
            else:
                cmds.append((ind, _MODE_BREAK, whitespace))
                cmds.append((ind, _MODE_BREAK, content))
            return
        remaining = Fill(parts[2:])
        second = parts[2]
        pair_flat = (ind, _MODE_FLAT, [content, whitespace, second])
        pair_fits = self._fits(pair_flat, [], rem, group_modes, True)
        cmds.append((ind, mode, remaining))
        if pair_fits:
            cmds.append((ind, _MODE_FLAT, whitespace))
            cmds.append(content_flat)
        elif content_fits:
            cmds.append((ind, _MODE_BREAK, whitespace))
            cmds.append(content_flat)
        else:
            cmds.append((ind, _MODE_BREAK, whitespace))
            cmds.append((ind, _MODE_BREAK, content))

    def _print_wrapped(self, ind: _Indentation, node: Wrapped, out: list[str], pos: int) -> int:
        texts: list[str]
        if node.lines is not None and all(
            (pos if i == 0 else ind.width) + len(line) <= self.width for i, line in enumerate(node.lines)
        ):
            texts = node.lines
        else:
            # Greedy word wrap: as many words per line as fit, at least one.
            # The first line starts where the printer is; later ones at the indent.
            texts = [
                (node.prefix + " ".join(words)).rstrip()
                for words in wrap_words(
                    node.words,
                    first=self.width - pos - len(node.prefix),
                    rest=self.width - ind.width - len(node.prefix),
                )
            ]
        for i, text in enumerate(texts):
            if i:
                out.append(self.eol + ind.text)
                pos = ind.width
            out.append(text)
            pos += len(text)
        return pos


def wrap_words(words: Sequence[str], first: int, rest: int) -> list[list[str]]:
    """Split words into lines no longer than the widths given, where possible."""
    lines: list[list[str]] = [[]]
    available = first
    length = 0
    for word in words:
        current = lines[-1]
        extra = len(word) + (1 if current else 0)
        if current and length + extra > available:
            lines.append([word])
            length = len(word)
            available = rest
        else:
            current.append(word)
            length += extra
    return lines


def _without_leading_space(doc: Doc) -> Doc:
    """A trailing comment's document, ``[" ", text]``, without its separating space."""
    if isinstance(doc, list) and doc and doc[0] == " ":
        return doc[1:]
    return doc


def _trim(out: list[str]) -> None:
    """Remove trailing spaces and tabs from the end of the output."""
    while out:
        trimmed = out[-1].rstrip(" \t")
        if trimmed:
            out[-1] = trimmed
            return
        out.pop()


def print_doc(doc: Doc, width: int, indent_unit: str = "    ", indent_width: int = 4, eol: str = "\n") -> str:
    return Printer(width, indent_unit, indent_width, eol).print(doc)
