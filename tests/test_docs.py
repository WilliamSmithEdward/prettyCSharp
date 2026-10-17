"""The README's before-and-after example is what the formatter prints."""

import re
from pathlib import Path

from prettycsharp import format_source

README = Path(__file__).parent.parent / "README.md"


def test_readme_example_is_current() -> None:
    text = README.read_text(encoding="utf-8")
    before = re.search(r"Before:\n\n```csharp\n(.*?)```", text, re.S)
    after = re.search(r"After:\n\n```csharp\n(.*?)```", text, re.S)
    assert before is not None and after is not None
    assert format_source(before.group(1)) == after.group(1)
