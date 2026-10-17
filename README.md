# prettycsharp

[![PyPI version](https://img.shields.io/pypi/v/prettycsharp)](https://pypi.org/project/prettycsharp/)
[![Python versions](https://img.shields.io/pypi/pyversions/prettycsharp)](https://pypi.org/project/prettycsharp/)
[![Downloads](https://static.pepy.tech/badge/prettycsharp/month)](https://pepy.tech/projects/prettycsharp)
[![CI](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/ci.yml)
[![Security](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/security.yml)
[![Malware scan](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/malware-scan.yml/badge.svg?branch=main)](https://github.com/WilliamSmithEdward/prettyCSharp/actions/workflows/malware-scan.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/WilliamSmithEdward/prettyCSharp/badge)](https://scorecard.dev/viewer/?uri=github.com/WilliamSmithEdward/prettyCSharp)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/WilliamSmithEdward/prettyCSharp/blob/main/LICENSE)

An opinionated formatter for C#, written in Python, in the spirit of Prettier.
It parses each file with [tree-sitter](https://tree-sitter.github.io/) and
reprints it in one canonical layout. It needs no .NET SDK.

## Status

In development, not yet released. The parser, the command line and the
refusal of files with syntax errors work today. The layout rules do not
exist yet, so every valid file comes back unchanged. The planned defaults
and the setting behind each one are in
[DESIGN.md](https://github.com/WilliamSmithEdward/prettyCSharp/blob/main/DESIGN.md).

## Install

Python 3.10 or later.

```bash
pip install prettycsharp
```

## Use

```bash
prettycsharp format src/
```
```bash
prettycsharp check src/
```
```bash
prettycsharp diff Order.cs
```

`format` rewrites files in place, `check` exits 1 when any file would
change, and `diff` prints a unified diff. `--write`, `--check` and `--diff`
are aliases. Given one file and no command, the formatted file goes to
stdout. A folder is searched for `.cs` files outside `bin/`, `obj/` and
hidden folders. A file that does not parse is reported and left untouched,
with exit status 2.

From Python:

```python
from prettycsharp import CSharpSyntaxError, format_source

formatted = format_source(source)
```

## License

[MIT](https://github.com/WilliamSmithEdward/prettyCSharp/blob/main/LICENSE)
