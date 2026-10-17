"""Coverage-guided fuzzing of the parser and the formatter on arbitrary text.

  format  format_source() either returns or raises CSharpSyntaxError, never
          anything else, and its output formats to itself again. The input
          bytes are the source, as UTF-8.

    python fuzz/fuzz_formatter.py <target> [libFuzzer options] [corpus dirs]
    python fuzz/fuzz_formatter.py format -max_total_time=60 tests/fuzz_corpus/csharp

The .github/workflows/fuzz.yml workflow runs each target from
tests/fuzz_corpus/csharp. A finding becomes a seed there, which
tests/test_fuzz_corpus.py replays on every CI run.
"""

import sys

import atheris

with atheris.instrument_imports():
    from prettycsharp import CSharpSyntaxError, format_source


def fuzz_format(data):
    text = data.decode("utf-8", errors="replace")
    try:
        output = format_source(text)
    except CSharpSyntaxError:
        return
    if format_source(output) != output:
        raise AssertionError("formatting the output changes it again")


TARGETS = {"format": fuzz_format}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        sys.exit(f"usage: fuzz_formatter.py <{'|'.join(TARGETS)}> [libFuzzer options]")
    atheris.Setup([sys.argv[0], *sys.argv[2:]], TARGETS[sys.argv[1]])
    atheris.Fuzz()


if __name__ == "__main__":
    main()
