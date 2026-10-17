"""Helpers shared by the tests."""

from __future__ import annotations

import textwrap

from prettycsharp import Settings, format_source


def fmt(source: str, **values: object) -> str:
    settings = Settings().with_values(values) if values else Settings()
    return format_source(textwrap.dedent(source).lstrip("\n"), settings)


def check(source: str, expected: str, **values: object) -> None:
    """``source`` formats to ``expected``, and ``expected`` formats to itself."""
    want = textwrap.dedent(expected).lstrip("\n")
    got = fmt(source, **values)
    assert got == want, f"\n--- got ---\n{got}\n--- want ---\n{want}"
    again = fmt(want, **values)
    assert again == want, f"not stable:\n{again}"
