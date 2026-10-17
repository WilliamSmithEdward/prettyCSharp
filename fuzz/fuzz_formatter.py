"""Coverage-guided fuzzing of the parser and the formatter on arbitrary text.

  format    format_source() with the default settings returns, or refuses
            the input with CSharpSyntaxError or FormattingError, never fails
            any other way, and its output formats to itself again. The input
            bytes are the source, as UTF-8.
  settings  The same, under the settings variant the first input byte picks;
            the rest is the source.

    python fuzz/fuzz_formatter.py <target> [libFuzzer options] [corpus dirs]
    python fuzz/fuzz_formatter.py format -max_total_time=60 tests/fuzz_corpus/csharp

The .github/workflows/fuzz.yml workflow runs each target from
tests/fuzz_corpus/csharp. A finding becomes a seed there, which
tests/test_fuzz_corpus.py replays on every CI run.
"""

import sys

import atheris

with atheris.instrument_imports():
    from prettycsharp import CSharpSyntaxError, FormattingError, Settings, format_source

VARIANTS = [
    Settings(),
    Settings().with_values({"brace_style": "kr", "continuation_keywords": "same_line", "indent_style": "tab"}),
    Settings().with_values({"expression_bodies": "block", "namespace_style": "block", "braces": "always"}),
    Settings().with_values({"max_line_length": 40, "argument_wrap": "fill", "parentheses": "remove_redundant"}),
    Settings().with_values({"chain_break_threshold": 0, "attributes": "combine", "trailing_commas": "add"}),
]


def check(text, settings):
    try:
        output = format_source(text, settings)
    except (CSharpSyntaxError, FormattingError):
        return
    if format_source(output, settings) != output:
        raise AssertionError("formatting the output changes it again")


def fuzz_format(data):
    check(data.decode("utf-8", errors="replace"), VARIANTS[0])


def fuzz_settings(data):
    if not data:
        return
    check(data[1:].decode("utf-8", errors="replace"), VARIANTS[data[0] % len(VARIANTS)])


TARGETS = {"format": fuzz_format, "settings": fuzz_settings}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        sys.exit(f"usage: fuzz_formatter.py <{'|'.join(TARGETS)}> [libFuzzer options]")
    atheris.Setup([sys.argv[0], *sys.argv[2:]], TARGETS[sys.argv[1]])
    atheris.Fuzz()


if __name__ == "__main__":
    main()
