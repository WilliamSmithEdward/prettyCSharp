"""Grammar gaps must not cause valid assignments to be skipped or changed."""

import pytest

from prettycsharp import CSharpSyntaxError, Settings, format_details
from prettycsharp.syntax import Node, build
from prettycsharp.verify import canonical

from support import check, fmt


@pytest.mark.parametrize("operator", ["=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", ">>>=", "??="])
def test_required_assignment(operator: str) -> None:
    check(f"required{operator}value;", f"required {operator} value;\n")


@pytest.mark.parametrize("target", ["a?.B", "a?[i]", "a?.B?.C", "a?.B?[i]", "a?[i]?.B", "a?.Get().B"])
@pytest.mark.parametrize("operator", ["=", "+=", "-=", "??="])
def test_null_conditional_assignment(target: str, operator: str) -> None:
    check(f"{target}{operator}value;", f"{target} {operator} value;\n")


def test_reported_required_assignments_in_a_loop() -> None:
    check(
        "long required=0;foreach(var index in indices){required=Math.Max(required,index+1);required-=range;}",
        "long required = 0;\n\nforeach (var index in indices)\n{\n"
        "    required = Math.Max(required, index + 1);\n    required -= range;\n}\n",
    )


def test_comments_literals_and_original_token_text_are_preserved() -> None:
    source = 'required /* keep */ = Get("required = x; a?.B = x;");\na?./* receiver */B = required;'
    output = fmt(source)
    assert '"required = x; a?.B = x;"' in output
    assert 'required /* keep */ = ' in output
    assert 'a?. /* receiver */B = required;' in output
    assert "req_ired" not in output
    assert fmt(output) == output


def test_required_member_modifier_is_preserved() -> None:
    check(
        "class C{public required string Name{get;init;}}",
        "class C\n{\n    public required string Name { get; init; }\n}\n",
    )


@pytest.mark.parametrize("source", ["required = ;", "required -= ;", "a?.B = ;", "a?[i] += ;", "a?. = 1;", "a?[] = 1;", "class { required = value; }", "a?.B = 1; class {"])
def test_invalid_input_remains_refused(source: str) -> None:
    with pytest.raises(CSharpSyntaxError):
        fmt(source)


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("a?.B = 1;", "a.B = 1;"),
        ("a?.B = 1;", "a!.B = 1;"),
        ("a?[i] = 1;", "a[i] = 1;"),
        ("a?.B += 1;", "a?.B = 1;"),
        ("required = 1;", "req_ired = 1;"),
    ],
)
def test_verifier_distinguishes_semantic_changes(before: str, after: str) -> None:
    assert canonical(build(before).root) != canonical(build(after).root)


def test_supported_syntax_needs_no_format_around_exclusions() -> None:
    result = format_details("required=1;a?.B=required;", Settings(syntax_errors="format_around"))
    assert result.text == "required = 1;\na?.B = required;\n"
    assert result.kept_lines == ()


def test_non_ascii_and_crlf_positions_are_preserved() -> None:
    source = 'var label="' + chr(0xE9) + '";\r\nrequired=1;\r\na?.B=required;\r\n'
    output = fmt(source)
    assert output == 'var label = "' + chr(0xE9) + '";\r\nrequired = 1;\r\na?.B = required;\r\n'
    assert fmt(output) == output


def test_nullable_types_and_ternary_collections_are_not_conditional_accesses() -> None:
    check(
        "required=1;string?[] values=ok?[1]:[2];a?.B=new string?[0];",
        "required = 1;\nstring?[] values = ok ? [1] : [2];\na?.B = new string?[0];\n",
    )


@pytest.mark.parametrize("access", ["a?.B", "a?[i]"])
def test_assignment_target_has_the_native_conditional_access_shape(access: str) -> None:
    assigned = build(f"{access} = value;")
    read = build(f"var value = {access};")
    # Compare actual syntax subtrees, without changing canonicalization.
    def conditional(node: Node) -> Node:
        stack = [node]
        while stack:
            current = stack.pop()
            if current.type == "conditional_access_expression":
                return current
            stack.extend(current.children)
        raise LookupError

    assert canonical(conditional(assigned.root)) == canonical(conditional(read.root))
