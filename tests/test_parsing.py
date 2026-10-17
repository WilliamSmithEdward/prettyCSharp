import pytest

from prettycsharp import CSharpSyntaxError, format_source
from prettycsharp.parsing import parse


def test_valid_source_parses() -> None:
    tree = parse("public class Order { public int Id { get; set; } }\n")
    assert tree.root_node.type == "compilation_unit"


def test_syntax_error_reports_its_position() -> None:
    with pytest.raises(CSharpSyntaxError) as raised:
        parse("public class Order\n{\n    public void Ship( {\n}\n")
    assert raised.value.line == 3


def test_format_source_refuses_invalid_source() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source("class {")


def test_format_source_keeps_valid_source() -> None:
    source = "namespace Shop;\r\n\r\npublic class Order { }\r\n"
    assert format_source(source) == source


def test_non_ascii_positions_are_reported() -> None:
    with pytest.raises(CSharpSyntaxError) as raised:
        parse('var s = "' + chr(0xE9) + "t" + chr(0xE9) + '";\nclass {')
    assert raised.value.line == 2


def test_deep_nesting_does_not_exhaust_the_stack() -> None:
    source = "class C { void M() { var x = " + "(" * 5000 + "1" + ")" * 4999 + "; } }"
    with pytest.raises(CSharpSyntaxError):
        parse(source)
