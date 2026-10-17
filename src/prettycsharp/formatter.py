"""The formatting entry point.

No layout rules exist yet: DESIGN.md describes them. Until they do,
``format_source`` validates that the input parses and returns it unchanged,
so every caller already gets the refusal behavior the finished formatter
will have.
"""

from __future__ import annotations

from prettycsharp.parsing import parse


def format_source(source: str) -> str:
    """Return ``source`` formatted, or raise CSharpSyntaxError."""
    parse(source)
    return source
