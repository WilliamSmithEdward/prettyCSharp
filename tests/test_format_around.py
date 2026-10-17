"""syntax_errors = "format_around": format everything but the lines the parser cannot read."""

from pathlib import Path

import pytest

from prettycsharp import CSharpSyntaxError, Settings, format_details, format_source
from prettycsharp.cli import main
from prettycsharp.isolate import isolate

AROUND = Settings().with_values({"syntax_errors": "format_around"})

NEW_SYNTAX = """class C
{
    void M()
    {
        Run();
          a?.B = 1;
        int   x=1;
    }

    void N() { Go(); }
}
"""


def test_skip_file_is_the_default() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source(NEW_SYNTAX)


def test_unreadable_line_is_kept_and_the_rest_formatted() -> None:
    result = format_details(NEW_SYNTAX, AROUND)
    assert result.text == (
        "class C\n{\n    void M()\n    {\n        Run();\n        a?.B = 1;\n        int x = 1;\n    }\n\n"
        "    void N() => Go();\n}\n"
    )
    assert result.kept_lines == (6,)
    assert format_source(result.text, AROUND) == result.text


def test_isolate_hides_the_fewest_lines() -> None:
    masked = isolate(NEW_SYNTAX)
    assert masked is not None
    assert list(masked.hidden.values()) == ["          a?.B = 1;"]


def test_file_scoped_directives_of_file_based_apps() -> None:
    source = "#:property PublishAot=false\n#:package Humanizer@3.0.0\nusing System;\nConsole.WriteLine( 1 );\n"
    result = format_details(source, AROUND)
    assert result.text == "#:property PublishAot=false\n#:package Humanizer@3.0.0\nusing System;\n\nConsole.WriteLine(1);\n"
    assert result.kept_lines == (1, 2)


def test_lines_inside_a_multi_line_string_keep_their_indentation() -> None:
    source = 'class C\n{\n  void M()\n  {\n      a?.B = """\n  x\n  """;\n  }\n}\n'
    result = format_details(source, AROUND)
    assert '      a?.B = """\n  x\n  """;' in result.text


def test_genuinely_broken_code_that_no_line_rescues_is_still_refused() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source("class {\n{\n{\n", AROUND)


SPLIT_AND_NEW = """#if NET
public sealed class Pool : IAsyncDisposable
#else
public sealed class Pool : IDisposable
#endif
{
    static public int Size=3;
    void M()
    {
        a?.B = 1;
        Run( );
    }
}
"""


def test_format_around_works_inside_each_if_view() -> None:
    result = format_details(SPLIT_AND_NEW, AROUND)
    assert result.text == (
        "#if NET\npublic sealed class Pool : IAsyncDisposable\n#else\npublic sealed class Pool : IDisposable\n#endif\n"
        "{\n    public static int Size = 3;\n\n    void M()\n    {\n        a?.B = 1;\n        Run();\n    }\n}\n"
    )
    assert result.kept_lines == (10,)
    assert format_source(result.text, AROUND) == result.text


def test_split_and_new_syntax_is_still_skipped_by_default() -> None:
    with pytest.raises(CSharpSyntaxError):
        format_source(SPLIT_AND_NEW)


def test_one_line_member_with_new_syntax_keeps_only_that_line() -> None:
    source = SPLIT_AND_NEW.replace("    void M()\n    {\n        a?.B = 1;\n        Run( );\n    }\n", "    void M() { a?.B = 1; Run( ); }\n")
    result = format_details(source, AROUND)
    assert "    public static int Size = 3;" in result.text
    assert "    void M() { a?.B = 1; Run( ); }" in result.text
    assert result.kept_lines == (8,)


def test_command_line_reports_the_kept_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "C.cs"
    path.write_text(NEW_SYNTAX)
    assert main(["format", str(path), "-o", "syntax_errors=format_around"]) == 0
    assert "line 6 left as written" in capsys.readouterr().err
    assert "int x = 1;" in path.read_text()
