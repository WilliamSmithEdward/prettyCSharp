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
reprints the whole file in one consistent layout: braces, indentation, line
breaks, blank lines, alignment and a few safe rewrites such as file-scoped
namespaces, sorted usings and expression-bodied members. It needs no .NET
SDK.

Before:

```csharp
using System;
using Microsoft.Extensions.Logging;
namespace Shop.Orders {
public class OrderService {
    static private readonly int MaxRetries=3;
    public decimal Total(Order order) { return order.Lines.Where(l => l.IsTaxable).Sum(l => l.Amount); }
    public void Ship(Order order) {
        if (order == null) return;
        if (order.IsPaid) { Send(order); } else { Hold(order); }
    }
}
}
```

After:

```csharp
using Microsoft.Extensions.Logging;
using System;

namespace Shop.Orders;

public class OrderService
{
    private static readonly int MaxRetries = 3;

    public decimal Total(Order order) =>
        order.Lines
            .Where(l => l.IsTaxable)
            .Sum(l => l.Amount);

    public void Ship(Order order)
    {
        if (order == null) return;

        if (order.IsPaid)
        {
            Send(order);
        }

        else
        {
            Hold(order);
        }
    }
}
```

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
stdout; `-` formats stdin to stdout, with `--stdin-filepath` naming the
path whose settings apply.

A target can be a `.cs` file, a folder, a `.csproj` (the files it
compiles, after its `Compile Include` and `Remove` items) or a `.sln` or
`.slnx` (every C# project in it). Folders are searched for `.cs` files.

| Option | Meaning |
| --- | --- |
| `-o KEY=VALUE`, `--option` | Set one setting, over every settings file. Repeatable. |
| `--config FILE` | Use this settings file instead of searching for one. |
| `--no-ignore` | Do not skip what `.gitignore` and `.prettycsharpignore` list. |
| `--stdin-filepath PATH` | The path stdin stands for. |

Exit status: 0 when nothing needs to change, 1 when `check` or `diff` found
a file that would change, 2 when a file could not be read, parsed or
formatted, or a setting is wrong. A file that does not parse is reported
and left untouched.

From Python:

```python
from prettycsharp import CSharpSyntaxError, FormattingError, Settings, format_details, format_source

formatted = format_source(source)
narrow = format_source(source, Settings().with_values({"max_line_length": 100}))

# format_details also says which lines were left as written (format_around).
result = format_details(source, Settings().with_values({"syntax_errors": "format_around"}))
print(result.text, result.kept_lines)
```

## Settings

Settings come from, highest precedence first:

1. `-o` options on the command line;
2. the nearest `.prettycsharp.toml`, or `pyproject.toml` with a
   `[tool.prettycsharp]` table, found by walking up from each file;
3. the standard keys of `.editorconfig` (`indent_style`, `indent_size`,
   `max_line_length`, `end_of_line`, `charset`, `insert_final_newline`,
   and the Roslyn keys for braces, `else`/`catch`/`finally` placement, using
   order, namespace style, braces and modifier order);
4. the defaults.

```toml
# .prettycsharp.toml
max_line_length = 100
brace_style = "kr"
continuation_keywords = "same_line"
align_assignments = false
```

Every setting, its default, its alternatives and an example of each layout
are in
[DESIGN.md](https://github.com/WilliamSmithEdward/prettyCSharp/blob/main/DESIGN.md).

## Skipping files and code

`bin/`, `obj/`, hidden folders and generated files (`*.g.cs`,
`*.Designer.cs`, and files marked `<auto-generated>`) are always skipped.
So is whatever `.gitignore` lists inside a git repository, and whatever a
`.prettycsharpignore` file lists, in gitignore syntax.

Inside a file, `// prettycsharp-ignore` leaves the next statement or member
as written, and `// prettycsharp-ignore-start` ... `// prettycsharp-ignore-end`
leaves everything between them as written.

## How it stays safe

Every output is parsed again and compared with the input as syntax trees,
with only the changes the settings allow (parentheses, modifier and using
order, attribute lists, trailing commas, expression bodies, namespace style,
braces and regions) taken out of the comparison. The comments must hold the
same words. If anything else differs, the file is not changed and the
command reports the difference. String literals, including verbatim, raw and
interpolated strings, are printed exactly as written.

## Conditional compilation

`#if` branches can split a declaration, as in:

```csharp
#if NET10_0_OR_GREATER
public sealed class Pool : IAsyncDisposable
#else
public sealed class Pool : IDisposable
#endif
{
```

Such a file is formatted the way the compiler reads it, one set of defined
symbols at a time: the directive lines and the inactive branches are set
aside, the rest is formatted, and they are put back as written. Symbol sets
are chosen so that every branch is active in one of them, so every branch
gets formatted. The result is checked under each symbol set, and a file
where any branch would change in meaning is left untouched.

## Code the parser cannot read

prettycsharp reads C# through tree-sitter's C# grammar, and syntax newer
than the grammar, such as C# 14's null-conditional assignment, does not
parse. By default such a file is reported with its line and column and left
untouched. With `syntax_errors = "format_around"`, the formatter finds the
fewest lines it cannot read, leaves just those as written, formats the rest,
and names the lines it kept:

```bash
prettycsharp format src/ -o syntax_errors=format_around
```

A file is still left untouched when hiding lines does not make it parse, as
when an `#if` stands inside an expression.

## License

[MIT](https://github.com/WilliamSmithEdward/prettyCSharp/blob/main/LICENSE)
