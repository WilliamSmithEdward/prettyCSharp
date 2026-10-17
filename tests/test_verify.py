"""The verifier: what it treats as the same code, and what it refuses."""

import pytest

from prettycsharp import CSharpSyntaxError
from prettycsharp.syntax import build
from prettycsharp.verify import VerificationError, canonical, verify


def same(a: str, b: str) -> bool:
    return canonical(build(a).root) == canonical(build(b).root)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("var x = (a);", "var x = a;"),
        ("class C { static public int X; }", "class C { public static int X; }"),
        ("using B;\nusing A;", "using A;\nusing B;"),
        ("[A, B] class C { }", "[A]\n[B] class C { }"),
        ("var p = new P { X = 1, };", "var p = new P { X = 1 };"),
        ("class C { int M() { return 1; } }", "class C { int M() => 1; }"),
        ("class C { void M() { Run(); } }", "class C { void M() => Run(); }"),
        ("class C { void M() { throw new E(); } }", "class C { void M() => throw new E(); }"),
        ("class C { int P { get { return 1; } } }", "class C { int P => 1; }"),
        ("namespace N { class C { } }", "namespace N;\nclass C { }"),
        ("void M() { if (a) Run(); }", "void M() { if (a) { Run(); } }"),
        ("void M() { lock (o) Run(); }", "void M() { lock (o) { Run(); } }"),
        ("class C {\n#region R\nint x;\n#endregion\n}", "class C { int x; }"),
    ],
)
def test_allowed_rewrites_are_the_same_code(before: str, after: str) -> None:
    assert same(before, after)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("var x = a * (b + c);", "var x = a * b + c;"),
        ('var s = "a  b";', 'var s = "a b";'),
        ("var x = a - -b;", "var x = a--b;"),
        ("int[,] m;", "int[] m;"),
        ("void M() { if (a) { A(); B(); } }", "void M() { if (a) A(); B(); }"),
    ],
)
def test_changes_of_meaning_are_different_code(before: str, after: str) -> None:
    try:
        changed = not same(before, after)
    except CSharpSyntaxError:
        # Output that no longer parses is refused before any comparison.
        changed = True
    assert changed


def test_verify_reports_where_the_code_changed() -> None:
    with pytest.raises(VerificationError, match="became"):
        verify(build("var x = a * (b + c);"), build("var x = a * b + c;"))


def test_verify_reports_lost_comments() -> None:
    with pytest.raises(VerificationError, match="comments changed"):
        verify(build("var x = 1; // note"), build("var x = 1;"))


def test_rewrapped_comments_are_the_same_words() -> None:
    verify(build("// one two\n// three\nclass C { }"), build("// one two three\nclass C { }"))
