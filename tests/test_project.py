from pathlib import Path

import pytest

from prettycsharp.project import (
    LATEST,
    clear_caches,
    compiled_files,
    framework_lang_version,
    lang_version_for,
    parse_lang_version,
    solution_projects,
)


@pytest.fixture(autouse=True)
def fresh_caches() -> None:
    clear_caches()


@pytest.mark.parametrize(
    ("framework", "version"),
    [
        ("net9.0", 13.0),
        ("net8.0-windows", 12.0),
        ("net6.0", 10.0),
        ("net5.0", 9.0),
        ("netcoreapp3.1", 8.0),
        ("netstandard2.1", 8.0),
        ("netstandard2.0", 7.3),
        ("net48", 7.3),
        ("unknown", None),
    ],
)
def test_framework_versions(framework: str, version: float | None) -> None:
    assert framework_lang_version(framework) == version


def test_lang_version_values() -> None:
    assert parse_lang_version("latest") == LATEST
    assert parse_lang_version("9.0") == 9.0
    assert parse_lang_version("10") == 10.0
    assert parse_lang_version("nonsense") is None


def test_lang_version_from_project_props_and_frameworks(tmp_path: Path) -> None:
    (tmp_path / "Directory.Build.props").write_text("<Project><PropertyGroup><LangVersion>8.0</LangVersion></PropertyGroup></Project>")
    app = tmp_path / "App"
    (app / "Sub").mkdir(parents=True)
    (app / "App.csproj").write_text("<Project><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>")
    assert lang_version_for(app / "Sub" / "A.cs") == 8.0
    lib = tmp_path / "Lib"
    lib.mkdir()
    (lib / "Lib.csproj").write_text(
        "<Project><PropertyGroup><LangVersion>latest</LangVersion><TargetFrameworks>net48;net8.0</TargetFrameworks></PropertyGroup></Project>"
    )
    assert lang_version_for(lib / "A.cs") == LATEST


def test_multiple_frameworks_use_the_oldest(tmp_path: Path) -> None:
    (tmp_path / "Lib.csproj").write_text(
        "<Project><PropertyGroup><TargetFrameworks>net8.0;netstandard2.0</TargetFrameworks></PropertyGroup></Project>"
    )
    assert lang_version_for(tmp_path / "A.cs") == 7.3


def test_no_project_means_no_version(tmp_path: Path) -> None:
    assert lang_version_for(tmp_path / "loose" / "A.cs") in (None, LATEST)


def test_malformed_project_is_tolerated(tmp_path: Path) -> None:
    (tmp_path / "Bad.csproj").write_text("<Project><PropertyGroup>")
    assert lang_version_for(tmp_path / "A.cs") == LATEST


def test_entity_expansion_is_refused(tmp_path: Path) -> None:
    (tmp_path / "Evil.csproj").write_text(
        '<?xml version="1.0"?><!DOCTYPE p [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;">]>'
        "<Project><PropertyGroup><LangVersion>&b;</LangVersion></PropertyGroup></Project>"
    )
    # defusedxml refuses the document, so the project gives no version.
    assert lang_version_for(tmp_path / "A.cs") == LATEST


def test_compiled_files_default_glob_include_and_remove(tmp_path: Path) -> None:
    for name in ("A.cs", "Sub/B.cs", "bin/C.cs", "obj/D.cs", "Removed/E.cs"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("class X { }\n")
    shared = tmp_path.parent / f"{tmp_path.name}-shared"
    shared.mkdir()
    (shared / "Shared.cs").write_text("class S { }\n")
    project = tmp_path / "App.csproj"
    project.write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><ItemGroup>'
        '<Compile Remove="Removed\\**" />'
        f'<Compile Include="..\\{shared.name}\\Shared.cs" />'
        "</ItemGroup></Project>"
    )
    names = sorted(p.name for p in compiled_files(project))
    assert names == ["A.cs", "B.cs", "Shared.cs"]


def test_compiled_files_without_default_items(tmp_path: Path) -> None:
    (tmp_path / "A.cs").write_text("class A { }\n")
    (tmp_path / "B.cs").write_text("class B { }\n")
    project = tmp_path / "Old.csproj"
    project.write_text(
        "<Project><PropertyGroup><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup>"
        '<ItemGroup><Compile Include="B.cs" /></ItemGroup></Project>'
    )
    assert [p.name for p in compiled_files(project)] == ["B.cs"]


def test_solution_projects_sln_and_slnx(tmp_path: Path) -> None:
    sln = tmp_path / "All.sln"
    sln.write_text(
        'Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "App", "src\\App\\App.csproj", "{A}"\nEndProject\n'
        'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "Folder", "Folder", "{B}"\nEndProject\n'
    )
    assert solution_projects(sln) == [tmp_path / "src/App/App.csproj"]
    slnx = tmp_path / "All.slnx"
    slnx.write_text('<Solution><Folder Name="/src/"><Project Path="src/Lib/Lib.csproj" /></Folder></Solution>')
    assert solution_projects(slnx) == [tmp_path / "src/Lib/Lib.csproj"]
