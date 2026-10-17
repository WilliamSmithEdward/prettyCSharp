"""The layout printer on its own."""

from prettycsharp.doc import (
    BREAK_PARENT,
    ENSURE_LINE,
    HARDLINE,
    LINE,
    SOFTLINE,
    TRIM_INDENT,
    Fill,
    IfBreak,
    LineSuffix,
    Wrapped,
    conditional_group,
    group,
    indent,
    join,
    print_doc,
)


def call(*args: str) -> object:
    return group(["f(", indent([SOFTLINE, join([",", LINE], list(args))]), SOFTLINE, ")"])


def test_group_fits_or_breaks() -> None:
    assert print_doc(call("aa", "bb"), 80) == "f(aa, bb)"
    assert print_doc(call("aa", "bb"), 6) == "f(\n    aa,\n    bb\n)"


def test_hardline_breaks_every_enclosing_group() -> None:
    assert print_doc(group(["a", LINE, group(["b", HARDLINE, "c"])]), 80) == "a\nb\nc"


def test_line_suffix_waits_for_the_end_of_the_line() -> None:
    doc = ["x", LineSuffix(" // note"), BREAK_PARENT, ";", HARDLINE, "y"]
    # Code after a pending comment goes to the next line.
    assert print_doc(doc, 80) == "x // note\n;\ny"


def test_two_line_suffixes_do_not_share_a_line() -> None:
    doc = ["a", LineSuffix(" // one"), LineSuffix(" // two"), HARDLINE]
    assert print_doc(doc, 80) == "a // one\n // two\n"


def test_ensure_line_breaks_only_after_code() -> None:
    assert print_doc(["a", ENSURE_LINE, "b"], 80) == "a\nb"
    assert print_doc([HARDLINE, ENSURE_LINE, "b"], 80) == "\nb"


def test_trim_indent_goes_to_column_zero() -> None:
    assert print_doc(indent([HARDLINE, TRIM_INDENT, "#if X", HARDLINE, "a"]), 80) == "\n#if X\n    a"


def test_if_break_follows_its_group() -> None:
    doc = group(["[", indent([SOFTLINE, "aaaa", IfBreak(",", "")]), SOFTLINE, "]"])
    assert print_doc(doc, 80) == "[aaaa]"
    assert print_doc(doc, 4) == "[\n    aaaa,\n]"


def test_fill_packs_as_many_as_fit() -> None:
    assert print_doc(Fill(["aa", LINE, "bb", LINE, "cc", LINE, "dd"]), 5) == "aa bb\ncc dd"


def test_conditional_group_takes_the_first_state_that_fits() -> None:
    hugged = ["f(x => ", group(["{", indent([HARDLINE, "body"]), HARDLINE, "}"], should_break=True), ")"]
    expanded = ["f(", indent([HARDLINE, "x => {...}"]), HARDLINE, ")"]
    assert print_doc(conditional_group([["f(x => {...})"], hugged, expanded]), 8) == "f(x => {\n    body\n})"


def test_wrapped_comment_lines_are_kept_unless_too_long() -> None:
    kept = Wrapped("// ", ["a", "b"], ["// a", "// b"])
    assert print_doc(kept, 80) == "// a\n// b"
    wrapped = Wrapped("// ", "one two three four".split(), ["// one two three four"])
    assert print_doc(wrapped, 12) == "// one two\n// three\n// four"


def test_trailing_spaces_are_trimmed_at_line_breaks() -> None:
    assert print_doc(["a ", HARDLINE, "b"], 80) == "a\nb"


def test_tabs_and_crlf() -> None:
    assert print_doc(indent([HARDLINE, "a"]), 80, "\t", 4, "\r\n") == "\r\n\ta"
