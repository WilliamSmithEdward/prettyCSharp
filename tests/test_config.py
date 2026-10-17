from pathlib import Path

import pytest

from prettycsharp.config import clear_caches, editorconfig_values, settings_for
from prettycsharp.settings import SettingsError


@pytest.fixture(autouse=True)
def fresh_caches() -> None:
    clear_caches()


def test_defaults_without_any_file(tmp_path: Path) -> None:
    assert settings_for(tmp_path / "A.cs").max_line_length == 120


def test_nearest_dedicated_file_wins(tmp_path: Path) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("max_line_length = 100\nindent_size = 2\n")
    inner = tmp_path / "src"
    inner.mkdir()
    (inner / ".prettycsharp.toml").write_text("max_line_length = 90\n")
    settings = settings_for(inner / "A.cs")
    assert settings.max_line_length == 90
    # The nearest file is used alone; settings files do not merge.
    assert settings.indent_size == 4


def test_pyproject_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.prettycsharp]\nbrace_style = 'kr'\n")
    assert settings_for(tmp_path / "A.cs").brace_style == "kr"


def test_pyproject_without_our_table_is_skipped(tmp_path: Path) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("brace_style = 'mixed'\n")
    inner = tmp_path / "pkg"
    inner.mkdir()
    (inner / "pyproject.toml").write_text("[tool.other]\nx = 1\n")
    assert settings_for(inner / "A.cs").brace_style == "mixed"


def test_bad_toml_is_reported(tmp_path: Path) -> None:
    (tmp_path / ".prettycsharp.toml").write_text("max_line_length = \n")
    with pytest.raises(SettingsError, match="prettycsharp.toml"):
        settings_for(tmp_path / "A.cs")


def test_editorconfig_maps_standard_keys(tmp_path: Path) -> None:
    (tmp_path / ".editorconfig").write_text(
        "root = true\n"
        "[*]\nindent_style = tab\nend_of_line = crlf\n"
        "[*.{cs,vb}]\nindent_size = 2\nmax_line_length = 100\ncharset = utf-8-bom\n"
        "insert_final_newline = false\ncsharp_new_line_before_open_brace = none\n"
        "csharp_new_line_before_else = false\ndotnet_sort_system_directives_first = true\n"
        "csharp_style_namespace_declarations = block_scoped:warning\ncsharp_prefer_braces = true:silent\n"
        "csharp_preferred_modifier_order = public,static,readonly:suggestion\n"
        "[*.json]\nindent_size = 8\n"
    )
    values = editorconfig_values((tmp_path / "A.cs").resolve())
    assert values == {
        "indent_style": "tab",
        "end_of_line": "crlf",
        "indent_size": 2,
        "max_line_length": 100,
        "charset": "utf-8-bom",
        "insert_final_newline": False,
        "brace_style": "kr",
        "continuation_keywords": "same_line",
        "using_order": "system_first",
        "namespace_style": "block",
        "braces": "always",
        "modifier_order": ["public", "static", "readonly"],
    }


def test_editorconfig_root_stops_the_search_and_nearer_files_win(tmp_path: Path) -> None:
    (tmp_path / ".editorconfig").write_text("[*.cs]\nindent_size = 8\n")
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / ".editorconfig").write_text("root = true\n[*.cs]\nindent_size = 3\nmax_line_length = 90\n")
    (project / "src" / ".editorconfig").write_text("[src/*.cs]\nmax_line_length = 10\n[*.cs]\nmax_line_length = 80\n")
    values = editorconfig_values((project / "src" / "A.cs").resolve())
    assert values["indent_size"] == 3
    assert values["max_line_length"] == 80


def test_editorconfig_path_globs(tmp_path: Path) -> None:
    (tmp_path / ".editorconfig").write_text("root = true\n[src/**/*.cs]\nindent_size = 2\n[{a,b}.cs]\nindent_size = 6\n")
    assert editorconfig_values((tmp_path / "src" / "x" / "A.cs").resolve())["indent_size"] == 2
    assert editorconfig_values((tmp_path / "b.cs").resolve())["indent_size"] == 6
    assert "indent_size" not in editorconfig_values((tmp_path / "c.cs").resolve())


def test_dedicated_file_beats_editorconfig_and_overrides_beat_both(tmp_path: Path) -> None:
    (tmp_path / ".editorconfig").write_text("root = true\n[*.cs]\nmax_line_length = 80\nindent_size = 2\n")
    (tmp_path / ".prettycsharp.toml").write_text("max_line_length = 100\n")
    settings = settings_for(tmp_path / "A.cs", {"indent_size": "3"})
    assert settings.max_line_length == 100
    assert settings.indent_size == 3
