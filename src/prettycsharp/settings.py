"""Every formatting setting, its default and the values it accepts.

DESIGN.md describes each one. ``Settings.with_values`` validates a mapping
of setting names to values, as read from a configuration file or the
command line, and raises ``SettingsError`` naming the first problem.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass

# The .NET modifier order (IDE0036's default), with the modifiers C# needs
# in a fixed place: `ref` just before `partial` or the type keyword, and
# `partial` last.
DOTNET_MODIFIER_ORDER = (
    "public",
    "private",
    "protected",
    "internal",
    "file",
    "static",
    "extern",
    "new",
    "virtual",
    "abstract",
    "sealed",
    "override",
    "readonly",
    "unsafe",
    "required",
    "volatile",
    "async",
)


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    indent_style: str = "space"
    indent_size: int = 4
    max_line_length: int = 120
    end_of_line: str = "preserve"
    charset: str = "preserve"
    insert_final_newline: bool = True
    trim_trailing_whitespace: bool = True
    lang_version: str = "auto"

    brace_style: str = "allman"
    continuation_keywords: str = "blank_line"
    braces: str = "preserve"
    empty_bodies: str = "inline"

    member_blank_lines: str = "group_fields"
    blank_lines_around_blocks: bool = True
    max_blank_lines: int = 1

    argument_wrap: str = "one_per_line"
    chain_break_threshold: int = 2
    expression_body_chain: str = "own_line"
    binary_wrap: str = "before_operator_paren_own_line"
    ternary_wrap: str = "before"
    lambda_body: str = "hug"

    initializer_break_threshold: int = 2
    simple_lists_inline: bool = True
    trailing_commas: str = "remove"

    align_switch_arms: bool = False
    align_assignments: bool = False
    align_enum_values: bool = False

    switch_case_indent: bool = True
    switch_case_blank_lines: bool = True

    namespace_style: str = "file_scoped_if_supported"
    using_order: str = "alphabetical"
    expression_bodies: str = "prefer"
    attributes: str = "separate"
    modifier_order: tuple[str, ...] | str = "dotnet"
    parentheses: str = "remove_obvious"
    regions: str = "preserve"

    comment_space: bool = True
    comment_wrap: bool = True

    respect_gitignore: bool = True
    syntax_errors: str = "skip_file"

    def with_values(self, values: Mapping[str, object], source: str = "settings") -> Settings:
        changes: dict[str, object] = {}
        for name, value in values.items():
            key = name.replace("-", "_")
            if key not in _FIELDS:
                raise SettingsError(f"{source}: unknown setting {name!r}")
            changes[key] = _validate(key, value, source)
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]

    @property
    def width(self) -> int:
        return self.max_line_length if self.max_line_length > 0 else 1_000_000

    @property
    def indent_unit(self) -> str:
        return "\t" if self.indent_style == "tab" else " " * self.indent_size

    @property
    def modifiers(self) -> tuple[str, ...] | None:
        """The modifier order to apply, or None to leave modifiers alone."""
        if self.modifier_order == "preserve":
            return None
        if self.modifier_order == "dotnet":
            return DOTNET_MODIFIER_ORDER
        assert isinstance(self.modifier_order, tuple)
        return self.modifier_order


_CHOICES: dict[str, tuple[str, ...]] = {
    "indent_style": ("space", "tab"),
    "end_of_line": ("preserve", "lf", "crlf", "cr"),
    "charset": ("preserve", "utf-8", "utf-8-bom"),
    "brace_style": ("allman", "kr", "mixed"),
    "continuation_keywords": ("blank_line", "new_line", "same_line"),
    "braces": ("preserve", "always", "single_line_only"),
    "empty_bodies": ("inline", "allman"),
    "member_blank_lines": ("group_fields", "all", "preserve"),
    "argument_wrap": ("one_per_line", "one_per_line_close_on_last", "fill", "align"),
    "expression_body_chain": ("own_line", "hang"),
    "binary_wrap": ("before_operator_paren_own_line", "before_operator", "after_operator"),
    "ternary_wrap": ("before", "after", "always"),
    "lambda_body": ("hug", "argument"),
    "trailing_commas": ("remove", "add", "preserve"),
    "namespace_style": ("file_scoped_if_supported", "file_scoped", "block", "preserve"),
    "using_order": ("alphabetical", "system_first", "system_first_grouped", "preserve"),
    "expression_bodies": ("prefer", "block", "properties_only", "preserve"),
    "attributes": ("separate", "combine", "preserve"),
    "parentheses": ("remove_obvious", "remove_redundant", "preserve"),
    "regions": ("preserve", "remove", "normalize"),
    "syntax_errors": ("skip_file", "format_around"),
}

_FIELDS = {f.name: f for f in dataclasses.fields(Settings)}

_KNOWN_MODIFIERS = frozenset(DOTNET_MODIFIER_ORDER) | {"const", "partial", "ref", "fixed", "scoped"}


def _validate(key: str, value: object, source: str) -> object:
    default = getattr(Settings(), key)
    where = f"{source}: {key}"
    if key == "modifier_order":
        if value in ("dotnet", "preserve"):
            return value
        names = value.split(",") if isinstance(value, str) else value
        if not isinstance(names, (list, tuple)) or not names:
            raise SettingsError(f"{where} must be 'dotnet', 'preserve' or a list of modifiers")
        order = tuple(str(name).strip() for name in names)
        unknown = [name for name in order if name not in _KNOWN_MODIFIERS]
        if unknown:
            raise SettingsError(f"{where}: unknown modifier {unknown[0]!r}")
        return order
    if key == "lang_version":
        text = str(value).strip().lower()
        if text in ("auto", "latest", "preview", "default", "latestmajor"):
            return "auto" if text == "auto" else "latest"
        try:
            float(text)
        except ValueError:
            raise SettingsError(f"{where} must be 'auto', 'latest' or a version such as 12") from None
        return text
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise SettingsError(f"{where} must be true or false")
    if isinstance(default, int):
        if isinstance(value, bool):
            raise SettingsError(f"{where} must be a whole number")
        try:
            number = int(str(value))
        except ValueError:
            raise SettingsError(f"{where} must be a whole number") from None
        if number < 0 or (key == "indent_size" and number == 0):
            raise SettingsError(f"{where} must be a positive number")
        return number
    text = str(value).strip().lower().replace("-", "_") if key != "charset" else str(value).strip().lower()
    choices = _CHOICES.get(key)
    if choices is not None and text not in choices:
        raise SettingsError(f"{where} must be one of {', '.join(choices)}")
    return text
