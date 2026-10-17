from pathlib import Path

import pytest

from prettycsharp import cli
from prettycsharp.cli import main

VALID = "public class Order { }\n"


def write(path: Path, text: str, bom: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((chr(0xFEFF) if bom else "").encode() + text.encode("utf-8"))
    return path


def test_check_passes_on_valid_files(tmp_path: Path) -> None:
    write(tmp_path / "Order.cs", VALID)
    assert main(["check", str(tmp_path)]) == 0
    assert main(["--check", str(tmp_path)]) == 0


def test_syntax_error_exits_2_and_leaves_file_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path / "Broken.cs", "class {")
    assert main(["format", str(path)]) == 2
    assert path.read_text() == "class {"
    assert "not formatted" in capsys.readouterr().err


def test_folders_skip_bin_obj_and_hidden(tmp_path: Path) -> None:
    write(tmp_path / "src" / "Order.cs", VALID)
    for skipped in ("bin", "obj", ".vs"):
        write(tmp_path / "src" / skipped / "Generated.cs", "class {")
    assert main(["check", str(tmp_path)]) == 0


def test_stdout_mode_prints_the_file_without_its_bom(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write(tmp_path / "Order.cs", VALID, bom=True)
    assert main([str(path)]) == 0
    assert capsys.readouterr().out == VALID


def test_format_keeps_bom_and_line_endings(tmp_path: Path) -> None:
    text = "public class Order\r\n{\r\n}\r\n"
    path = write(tmp_path / "Order.cs", text, bom=True)
    assert main(["format", str(path)]) == 0
    assert path.read_bytes() == b"\xef\xbb\xbf" + text.encode()


def test_format_rewrites_a_changed_file_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No layout rule changes anything yet, so a stand-in formatter does.
    monkeypatch.setattr(cli, "format_source", lambda text: text + "// formatted\r\n")
    text = "public class Order\r\n{\r\n}\r\n"
    path = write(tmp_path / "Order.cs", text, bom=True)
    assert main(["check", str(path)]) == 1
    assert main(["format", str(path)]) == 0
    assert path.read_bytes() == b"\xef\xbb\xbf" + (text + "// formatted\r\n").encode()
    assert [p.name for p in tmp_path.iterdir()] == ["Order.cs"]


def test_failed_write_leaves_the_original(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "format_source", lambda text: text + "// formatted\n")

    def refuse(source: object, target: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(cli.os, "replace", refuse)
    path = write(tmp_path / "Order.cs", VALID)
    assert main(["format", str(path)]) == 2
    assert path.read_text() == VALID
    assert [p.name for p in tmp_path.iterdir()] == ["Order.cs"]


def test_unreadable_file_exits_2(tmp_path: Path) -> None:
    path = tmp_path / "Latin1.cs"
    path.write_bytes(b"// caf\xe9\n")
    assert main(["check", str(path)]) == 2


def test_conflicting_subcommand_and_flag_is_refused(tmp_path: Path) -> None:
    path = write(tmp_path / "Order.cs", VALID)
    with pytest.raises(SystemExit) as raised:
        main(["check", "--write", str(path)])
    assert raised.value.code == 2


def test_stdout_mode_needs_exactly_one_file(tmp_path: Path) -> None:
    write(tmp_path / "A.cs", VALID)
    write(tmp_path / "B.cs", VALID)
    with pytest.raises(SystemExit):
        main([str(tmp_path)])
