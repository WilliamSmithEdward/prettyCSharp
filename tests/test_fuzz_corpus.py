"""Replays every fuzz seed through the properties fuzz/fuzz_formatter.py checks."""

from pathlib import Path

import pytest

from prettycsharp import CSharpSyntaxError, FormattingError, Settings, format_source

CORPUS = Path(__file__).parent / "fuzz_corpus" / "csharp"
SEEDS = sorted(CORPUS.iterdir())
VARIANTS = [
    Settings(),
    Settings().with_values({"brace_style": "kr", "continuation_keywords": "same_line", "indent_style": "tab"}),
    Settings().with_values({"expression_bodies": "block", "namespace_style": "block", "braces": "always"}),
    Settings().with_values({"max_line_length": 40, "argument_wrap": "fill", "parentheses": "remove_redundant"}),
    Settings().with_values({"chain_break_threshold": 0, "attributes": "combine", "trailing_commas": "add"}),
]


def test_corpus_is_not_empty() -> None:
    assert SEEDS


@pytest.mark.parametrize("variant", range(len(VARIANTS)))
@pytest.mark.parametrize("seed", SEEDS, ids=lambda path: path.name)
def test_seed_formats_stably(seed: Path, variant: int) -> None:
    text = seed.read_bytes().decode("utf-8", errors="replace")
    settings = VARIANTS[variant]
    try:
        output = format_source(text, settings)
    except (CSharpSyntaxError, FormattingError):
        return
    assert format_source(output, settings) == output
