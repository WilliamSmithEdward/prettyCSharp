"""What MSBuild project files say: the C# version and the files compiled.

Project files are untrusted input, so they are parsed with defusedxml,
which refuses entity expansion and external references.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any

from defusedxml import ElementTree

from prettycsharp.ignore import glob_regex

# The parsed XML element. Only defusedxml parses here, and it has no type
# information, so elements are typed loosely rather than imported from xml.
Element = Any

LATEST = 99.0

# The default C# version of each target framework.
_FRAMEWORK_VERSIONS = (
    (r"^netcoreapp3\.", 8.0),
    (r"^netcoreapp[12]\.", 7.3),
    (r"^netstandard2\.1", 8.0),
    (r"^netstandard", 7.3),
    (r"^net[1-4]\d*$", 7.3),
)


def lang_version_for(source: Path) -> float | None:
    """The C# version of the project holding ``source``, or None if it has none."""
    project = find_project(source.resolve().parent)
    if project is None:
        return None
    return project_lang_version(project)


@cache
def find_project(directory: Path) -> Path | None:
    for folder in (directory, *directory.parents):
        try:
            projects = sorted(folder.glob("*.csproj"))
        except OSError:
            return None
        if projects:
            return projects[0]
    return None


@cache
def project_lang_version(project: Path) -> float:
    properties = _properties(project)
    version = properties.get("langversion")
    if version:
        parsed = parse_lang_version(version)
        if parsed is not None:
            return parsed
    frameworks = properties.get("targetframeworks") or properties.get("targetframework") or ""
    versions = [framework_lang_version(f.strip()) for f in frameworks.split(";") if f.strip()]
    known = [v for v in versions if v is not None]
    return min(known) if known else LATEST


def parse_lang_version(text: str) -> float | None:
    value = text.strip().lower()
    if value in ("latest", "latestmajor", "preview", "default", ""):
        return LATEST
    if value.startswith("iso-"):
        return 2.0
    try:
        return float(value)
    except ValueError:
        return None


def framework_lang_version(framework: str) -> float | None:
    """The default C# version of a target framework moniker."""
    name = framework.lower()
    modern = re.match(r"^net(\d+)\.\d+", name)
    if modern:
        major = int(modern.group(1))
        # net5.0 is C# 9, net6.0 C# 10, and each release since adds one.
        return 7.3 if major < 5 else 9.0 + (major - 5)
    for prefix, version in _FRAMEWORK_VERSIONS:
        if re.match(prefix, name):
            return version
    return None


def _properties(project: Path) -> dict[str, str]:
    """LangVersion and target frameworks, from Directory.Build.props and the project."""
    values: dict[str, str] = {}
    props = _find_upward(project.parent, "Directory.Build.props")
    for path in ([props] if props is not None else []) + [project]:
        root = _parse(path)
        if root is None:
            continue
        for element in root.iter():
            tag = _local(element.tag).lower()
            if tag in ("langversion", "targetframework", "targetframeworks") and element.text:
                values[tag] = element.text.strip()
    return values


def _find_upward(directory: Path, name: str) -> Path | None:
    for folder in (directory, *directory.parents):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def _parse(path: Path) -> Element | None:
    try:
        root: Element = ElementTree.parse(str(path)).getroot()
        return root
    except Exception:  # noqa: BLE001 - an unreadable project only loses its settings
        return None


def _local(tag: object) -> str:
    text = str(tag)
    return text.split("}", 1)[1] if text.startswith("{") else text


# Compiled files ------------------------------------------------------------


def compiled_files(project: Path) -> list[Path]:
    """The .cs files a project compiles: MSBuild's default glob, then Include and Remove."""
    root = _parse(project)
    folder = project.parent
    files: list[Path] = []
    default = True
    includes: list[str] = []
    removes: list[str] = []
    if root is not None:
        for element in root.iter():
            tag = _local(element.tag).lower()
            if tag == "enabledefaultcompileitems" and (element.text or "").strip().lower() == "false":
                default = False
            elif tag == "compile":
                if element.get("Include"):
                    includes.extend(_split_items(element.get("Include") or ""))
                if element.get("Remove"):
                    removes.extend(_split_items(element.get("Remove") or ""))
    if default:
        for path in sorted(folder.rglob("*.cs")):
            parts = path.relative_to(folder).parts[:-1]
            if not any(p.lower() in ("bin", "obj") for p in parts):
                files.append(path)
    for pattern in includes:
        files.extend(_glob(folder, pattern))
    removed = [re.compile(glob_regex(_normalize(p))) for p in removes]
    result: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen:
            continue
        try:
            relative = path.resolve().relative_to(folder.resolve()).as_posix()
        except ValueError:
            relative = None
        if relative is not None and any(r.fullmatch(relative) for r in removed):
            continue
        seen.add(resolved)
        result.append(path)
    return result


def _split_items(text: str) -> list[str]:
    return [item.strip() for item in text.split(";") if item.strip() and "$(" not in item]


def _normalize(pattern: str) -> str:
    return pattern.replace("\\", "/")


def _glob(folder: Path, pattern: str) -> list[Path]:
    normalized = _normalize(pattern)
    if any(c in normalized for c in "*?"):
        return sorted(p for p in folder.glob(normalized) if p.suffix.lower() == ".cs")
    path = folder / normalized
    return [path] if path.is_file() else []


def solution_projects(solution: Path) -> list[Path]:
    """The C# projects a .sln or .slnx lists."""
    projects: list[Path] = []
    if solution.suffix.lower() == ".slnx":
        root = _parse(solution)
        if root is not None:
            for element in root.iter():
                path = element.get("Path")
                if _local(element.tag).lower() == "project" and path and path.lower().endswith(".csproj"):
                    projects.append(solution.parent / _normalize(path))
        return projects
    try:
        text = solution.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return projects
    for match in re.finditer(r'^Project\("[^"]*"\)\s*=\s*"[^"]*",\s*"([^"]+\.csproj)"', text, re.M | re.I):
        projects.append(solution.parent / _normalize(match.group(1)))
    return projects


def clear_caches() -> None:
    find_project.cache_clear()
    project_lang_version.cache_clear()
