"""Finding the settings for a source file.

Settings come from, highest precedence first: the command line, the
nearest ``.prettycsharp.toml`` or ``pyproject.toml`` with a
``[tool.prettycsharp]`` table, the standard keys of ``.editorconfig``, and
the defaults in ``Settings``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from prettycsharp.settings import Settings, SettingsError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10 only
    import tomli as tomllib

CONFIG_NAME = ".prettycsharp.toml"


def settings_for(path: Path, overrides: Mapping[str, object] | None = None, config_file: Path | None = None) -> Settings:
    """The settings for the source file at ``path``."""
    directory = path.resolve().parent
    settings = Settings()
    settings = settings.with_values(editorconfig_values(path.resolve()), ".editorconfig")
    if config_file is not None:
        values, source = read_config(config_file.resolve())
    else:
        found = find_config(directory)
        values, source = ({}, "") if found is None else read_config(found)
    if values:
        settings = settings.with_values(values, source)
    if overrides:
        settings = settings.with_values(overrides, "command line")
    return settings


@cache
def find_config(directory: Path) -> Path | None:
    """The nearest .prettycsharp.toml, or pyproject.toml with our table, at or above ``directory``."""
    for folder in (directory, *directory.parents):
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return candidate
        pyproject = folder / "pyproject.toml"
        if pyproject.is_file() and "prettycsharp" in _tool_tables(_load_toml(pyproject)):
            return pyproject
    return None


def _tool_tables(data: dict[str, object]) -> dict[str, object]:
    tool = data.get("tool", {})
    return tool if isinstance(tool, dict) else {}


@cache
def read_config(path: Path) -> tuple[dict[str, object], str]:
    data = _load_toml(path)
    table: object = _tool_tables(data).get("prettycsharp", {}) if path.name == "pyproject.toml" else data
    if not isinstance(table, dict):
        raise SettingsError(f"{path}: [tool.prettycsharp] must be a table")
    return dict(table), str(path)


def _load_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"{path}: {error}") from None
    except OSError as error:
        raise SettingsError(f"{path}: cannot read: {error}") from None


# .editorconfig ------------------------------------------------------------


def editorconfig_values(path: Path) -> dict[str, object]:
    """Our settings from the .editorconfig files that apply to ``path``."""
    files: list[Path] = []
    for folder in path.parents:
        candidate = folder / ".editorconfig"
        if candidate.is_file():
            files.append(candidate)
            if _parse_editorconfig(candidate)[0]:
                break
    raw: dict[str, str] = {}
    # The file nearest the source wins, so apply the farthest first.
    for config in reversed(files):
        _, sections = _parse_editorconfig(config)
        relative = path.relative_to(config.parent).as_posix()
        for pattern, values in sections:
            if _section_matches(pattern, relative):
                raw.update(values)
    return _map_editorconfig(raw)


@cache
def _parse_editorconfig(path: Path) -> tuple[bool, tuple[tuple[str, dict[str, str]], ...]]:
    root = False
    sections: list[tuple[str, dict[str, str]]] = []
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError):
        return False, ()
    for line in lines:
        text = line.strip()
        if not text or text[0] in "#;":
            continue
        if text.startswith("[") and text.endswith("]"):
            sections.append((text[1:-1], {}))
            continue
        if "=" not in text:
            continue
        key, value = (part.strip() for part in text.split("=", 1))
        key = key.lower()
        if not sections:
            if key == "root":
                root = value.lower() == "true"
            continue
        sections[-1][1][key] = value
    return root, tuple(sections)


def _section_matches(pattern: str, relative: str) -> bool:
    if "/" not in pattern:
        pattern = "**/" + pattern
    elif pattern.startswith("/"):
        pattern = pattern[1:]
    return re.fullmatch(_editorconfig_regex(pattern), relative) is not None


@cache
def _editorconfig_regex(pattern: str) -> str:
    out: list[str] = []
    i = 0
    depth = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\" and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        if c == "*":
            if pattern[i : i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            end = pattern.find("]", i + 1)
            if end < 0:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1 : end]
                negate = body.startswith("!")
                body = body[1:] if negate else body
                out.append("[" + ("^" if negate else "") + body.replace("\\", "\\\\") + "]")
                i = end + 1
                continue
        elif c == "{":
            end = pattern.find("}", i)
            body = pattern[i + 1 : end] if end > 0 else ""
            numbers = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", body)
            if end > 0 and numbers:
                low, high = sorted(int(n) for n in numbers.groups())
                out.append("(?:" + "|".join(str(n) for n in range(low, high + 1)) + ")")
                i = end + 1
                continue
            if end > 0 and "," in body:
                out.append("(?:")
                depth += 1
            else:
                out.append(re.escape(c))
        elif c == "," and depth:
            out.append("|")
        elif c == "}" and depth:
            out.append(")")
            depth -= 1
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _map_editorconfig(raw: Mapping[str, str]) -> dict[str, object]:
    values: dict[str, object] = {}

    def text(key: str) -> str | None:
        value = raw.get(key)
        if value is None:
            return None
        # Roslyn options can carry a severity: true:warning.
        return value.split(":")[0].strip().lower()

    style = text("indent_style")
    if style in ("space", "tab"):
        values["indent_style"] = style
    size = text("indent_size")
    if size is not None and size.isdigit() and int(size) > 0:
        values["indent_size"] = int(size)
    elif size == "tab":
        width = text("tab_width")
        if width is not None and width.isdigit() and int(width) > 0:
            values["indent_size"] = int(width)
    length = text("max_line_length")
    if length is not None and length.isdigit():
        values["max_line_length"] = int(length)
    elif length == "off":
        values["max_line_length"] = 0
    eol = text("end_of_line")
    if eol in ("lf", "crlf", "cr"):
        values["end_of_line"] = eol
    charset = text("charset")
    if charset in ("utf-8", "utf-8-bom"):
        values["charset"] = charset
    for key in ("insert_final_newline", "trim_trailing_whitespace"):
        flag = text(key)
        if flag in ("true", "false"):
            values[key] = flag == "true"
    brace = text("csharp_new_line_before_open_brace")
    if brace == "all":
        values["brace_style"] = "allman"
    elif brace == "none":
        values["brace_style"] = "kr"
    if any(text(f"csharp_new_line_before_{k}") == "false" for k in ("else", "catch", "finally")):
        values["continuation_keywords"] = "same_line"
    if text("dotnet_sort_system_directives_first") == "true":
        values["using_order"] = "system_first"
    namespaces = text("csharp_style_namespace_declarations")
    if namespaces == "file_scoped":
        values["namespace_style"] = "file_scoped"
    elif namespaces == "block_scoped":
        values["namespace_style"] = "block"
    braces = text("csharp_prefer_braces")
    if braces == "true":
        values["braces"] = "always"
    elif braces == "when_multiline":
        values["braces"] = "single_line_only"
    elif braces == "false":
        values["braces"] = "preserve"
    order = raw.get("csharp_preferred_modifier_order")
    if order:
        values["modifier_order"] = [m.strip() for m in order.split(":")[0].split(",") if m.strip()]
    return values


def clear_caches() -> None:
    find_config.cache_clear()
    read_config.cache_clear()
    _parse_editorconfig.cache_clear()
