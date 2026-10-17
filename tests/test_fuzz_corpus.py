"""Replays every fuzz seed through the property fuzz/fuzz_formatter.py checks."""

from pathlib import Path

import pytest

from prettycsharp import CSharpSyntaxError, format_source

CORPUS = Path(__file__).parent / "fuzz_corpus" / "csharp"
SEEDS = sorted(CORPUS.iterdir())


def test_corpus_is_not_empty() -> None:
    assert SEEDS


@pytest.mark.parametrize("seed", SEEDS, ids=lambda path: path.name)
def test_seed_formats_stably(seed: Path) -> None:
    text = seed.read_bytes().decode("utf-8", errors="replace")
    try:
        output = format_source(text)
    except CSharpSyntaxError:
        return
    assert format_source(output) == output
