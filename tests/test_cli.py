import io
from pathlib import Path

import pytest

from prettycsharp import cli
from prettycsharp.cli import main

FORMATTED = "public class Order { }\n"
MESSY = "public class Order\n{\n}\n"


def write(path: Path, text: str, bom: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((chr(0xFEFF) if bom else "").encode() + text.encode("utf-8"))
    return path


def test_check_passes_on_formatted_files_and_fails_on_others(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write(tmp_path / "Order.cs", FORMATTED)
    assert main(["check", str(tmp_path)]) == 0
    assert main(["--check", str(tmp_path)]) == 0
    messy = write(tmp_path / "Messy.cs", MESSY)
    assert main(["check", str(tmp_path)]) == 1
    assert f"would format {messy}" in capsys.readouterr().out


def test_format_rewrites_files_in_place(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "Order.cs", MESSY)
    assert main(["format", str(path)]) == 0
    assert path.read_text() == FORMATTED
    assert "formatted" in capsys.readouterr().out
    assert main(["--write", str(path)]) == 0
    assert [p.name for p in tmp_path.iterdir()] == ["Order.cs"]


def test_diff_prints_a_unified_diff(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "Order.cs", MESSY)
    assert main(["diff", str(path)]) == 1
    out = capsys.readouterr().out
    assert "-public class Order\n" in out and "+public class Order { }\n" in out
    assert path.read_text() == MESSY


def test_stdout_mode_prints_the_file_without_its_bom(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "Order.cs", MESSY, bom=True)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == FORMATTED


def test_stdin_to_stdout(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(MESSY))
    assert main(["-"]) == 0
    assert capsys.readouterr().out == FORMATTED


def test_stdin_uses_the_settings_of_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("brace_style = 'kr'\n")
    monkeypatch.setattr("sys.stdin", io.StringIO("class A { void M() { A(); B(); } }"))
    assert main(["-", "--stdin-filepath", str(tmp_path / "A.cs")]) == 0
    assert capsys.readouterr().out.startswith("class A {\n")


def test_syntax_error_exits_2_and_leaves_the_file_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path / "Broken.cs", "class {")
    assert main(["format", str(path)]) == 2
    assert path.read_text() == "class {"
    assert "not formatted" in capsys.readouterr().err


def test_format_keeps_bom_and_line_endings(tmp_path: Path) -> None:
    path = write(tmp_path / "Order.cs", "public class Order\r\n{\r\n}\r\n", bom=True)
    assert main(["format", str(path)]) == 0
    assert path.read_bytes() == b"\xef\xbb\xbfpublic class Order { }\r\n"


def test_charset_setting_adds_or_removes_the_bom(tmp_path: Path) -> None:
    path = write(tmp_path / "Order.cs", FORMATTED)
    assert main(["format", str(path), "-o", "charset=utf-8-bom"]) == 0
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert main(["format", str(path), "-o", "charset=utf-8"]) == 0
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_options_override_settings_files(tmp_path: Path) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("max_line_length = 200\n")
    path = write(tmp_path / "A.cs", "var x = Call(alpha, beta, gamma);\n")
    assert main(["format", str(path), "--option", "max_line_length=20"]) == 0
    assert path.read_text() == "var x = Call(\n    alpha,\n    beta,\n    gamma\n);\n"


def test_explicit_config_file(tmp_path: Path) -> None:
    config = tmp_path / "custom.toml"
    config.write_text("indent_size = 2\n")
    path = write(tmp_path / "A.cs", "class A { void M() { A(); B(); } }\n")
    assert main(["format", str(path), "--config", str(config)]) == 0
    assert "\n  void M()" in path.read_text()


def test_bad_settings_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("brace_style = 'gnu'\n")
    path = write(tmp_path / "A.cs", FORMATTED)
    assert main(["check", str(path)]) == 2
    assert "brace_style must be one of" in capsys.readouterr().err
    assert main(["check", str(path), "-o", "nonsense"]) == 2
    assert main(["check", str(path), "--config", str(tmp_path / "missing.toml")]) == 2


def test_folders_skip_bin_obj_hidden_and_generated_files(tmp_path: Path) -> None:
    write(tmp_path / "src" / "Order.cs", FORMATTED)
    for skipped in ("bin", "obj", ".vs"):
        write(tmp_path / "src" / skipped / "Generated.cs", "class {")
    write(tmp_path / "src" / "Form.Designer.cs", "class {")
    write(tmp_path / "src" / "Api.g.cs", "class {")
    write(tmp_path / "src" / "Marked.cs", "// <auto-generated/>\nclass {")
    assert main(["check", str(tmp_path)]) == 0


def test_ignore_files_and_no_ignore(tmp_path: Path) -> None:
    write(tmp_path / "Legacy" / "Old.cs", MESSY)
    write(tmp_path / ".prettycsharpignore", "Legacy/\n")
    assert main(["check", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path), "--no-ignore"]) == 1


def test_respect_gitignore_setting(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path / ".gitignore", "Vendor/\n")
    write(tmp_path / "Vendor" / "Lib.cs", MESSY)
    assert main(["check", str(tmp_path)]) == 0
    write(tmp_path / ".prettycsharp.toml", "respect_gitignore = false\n")
    assert main(["check", str(tmp_path)]) == 1


def test_project_and_solution_targets(tmp_path: Path) -> None:
    project = tmp_path / "App" / "App.csproj"
    project.parent.mkdir()
    project.write_text('<Project Sdk="Microsoft.NET.Sdk"><ItemGroup><Compile Remove="Skip.cs" /></ItemGroup></Project>')
    write(tmp_path / "App" / "Order.cs", MESSY)
    write(tmp_path / "App" / "Skip.cs", "class {")
    solution = tmp_path / "App.sln"
    solution.write_text(
        'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "App\\App.csproj", "{11111111-1111-1111-1111-111111111111}"\nEndProject\n'
    )
    assert main(["check", str(project)]) == 1
    assert main(["check", str(solution)]) == 1
    assert main(["format", str(solution)]) == 0
    assert (tmp_path / "App" / "Order.cs").read_text() == FORMATTED


def test_lang_version_comes_from_the_project(tmp_path: Path) -> None:
    project = tmp_path / "App.csproj"
    project.write_text("<Project><PropertyGroup><TargetFramework>net48</TargetFramework></PropertyGroup></Project>")
    path = write(tmp_path / "A.cs", "namespace A;\n\nclass B { }\n")
    assert main(["format", str(path)]) == 0
    assert path.read_text() == "namespace A\n{\n    class B { }\n}\n"


def test_missing_path_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", str(tmp_path / "nowhere")]) == 2
    assert "no such file or folder" in capsys.readouterr().err


def test_unreadable_file_exits_2(tmp_path: Path) -> None:
    path = tmp_path / "Latin1.cs"
    path.write_bytes(b"// caf\xe9\n")
    assert main(["check", str(path)]) == 2


def test_failed_write_leaves_the_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(source: object, target: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(cli.os, "replace", refuse)
    path = write(tmp_path / "Order.cs", MESSY)
    assert main(["format", str(path)]) == 2
    assert path.read_text() == MESSY
    assert [p.name for p in tmp_path.iterdir()] == ["Order.cs"]


def test_conflicting_subcommand_and_flag_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path / "Order.cs", FORMATTED)
    with pytest.raises(SystemExit) as raised:
        main(["check", "--write", str(path)])
    assert raised.value.code == 2


def test_stdout_mode_needs_exactly_one_file(tmp_path: Path) -> None:
    write(tmp_path / "A.cs", FORMATTED)
    write(tmp_path / "B.cs", FORMATTED)
    with pytest.raises(SystemExit):
        main([str(tmp_path)])


def test_stdin_cannot_mix_with_paths(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["-", str(tmp_path)])
