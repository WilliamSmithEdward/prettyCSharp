# prettycsharp design

An opinionated formatter for C#, written in Python, in the spirit of Prettier. It parses each
file and reprints the whole file in one canonical layout. It does not report lint diagnostics.

## Foundations

| Decision | Choice |
| --- | --- |
| Package, command, import name | `prettycsharp` |
| Python | 3.10+ |
| Parser | tree-sitter-c-sharp through the py-tree-sitter bindings. No .NET dependency. |
| Model | Prettier-style reprinter only. No rule engine, no diagnostics. |
| Inputs | A `.cs` file, a folder, a `.csproj` (the files it compiles), a `.sln` or `.slnx`, or stdin |
| Safety | Every output is reparsed and its tree compared to the input's, ignoring whitespace and the rewrites listed below; the comments must hold the same words. A mismatch leaves the file untouched and reports an error. Files that already contain syntax errors are skipped with a message. |

The printer is a Prettier-style layout engine (`doc.py`): handlers turn each
syntax node into groups, indents and line breaks, and the engine fits them to
the line width. Comments are attached to tokens, so a handler that rearranges
tokens cannot drop one. String literals of every kind are single tokens
printed exactly as written.

## Command line

Subcommands, with Prettier-style flags as aliases.

```bash
prettycsharp format src/
```
```bash
prettycsharp check src/
```
```bash
prettycsharp diff Order.cs
```

| Subcommand | Flag alias | Behavior |
| --- | --- | --- |
| `format` | `--write` | Rewrite files in place |
| `check` | `--check` | Exit 1 if any file would change. For CI. |
| `diff` | `--diff` | Print a unified diff, change nothing |
| (none) | (none) | Print the formatted file to stdout |

`-` formats stdin to stdout. `-o KEY=VALUE` sets one setting, `--config FILE`
names the settings file, `--no-ignore` turns off `.gitignore` and
`.prettycsharpignore`, and `--stdin-filepath` names the path stdin stands for.
Exit status is 0 when nothing changes, 1 when `check` or `diff` finds work,
and 2 on any error. Writes go to a temporary file swapped in afterwards.

## Configuration

Settings are resolved per source file, highest precedence first:

1. Command-line options
2. `.prettycsharp.toml`, or `[tool.prettycsharp]` in `pyproject.toml`, the nearest one walking
   up from the source file
3. `.editorconfig`, standard keys only (mapping below)
4. Built-in defaults (the tables below)

The nearest settings file is used on its own; files at different levels do not
merge. Unknown settings and bad values are errors. Every behavior with a
setting name below can be overridden. The defaults are one person's style,
and any team can change any of them.

### .editorconfig mapping

| .editorconfig key | prettycsharp setting |
| --- | --- |
| `indent_style`, `indent_size` | `indent_style`, `indent_size` |
| `max_line_length` | `max_line_length` |
| `end_of_line` | `end_of_line` |
| `charset` | `charset` |
| `insert_final_newline` | `insert_final_newline` |
| `trim_trailing_whitespace` | `trim_trailing_whitespace` |
| `csharp_new_line_before_open_brace` | `brace_style` (`all` is `allman`, `none` is `kr`) |
| `csharp_new_line_before_else`, `_catch`, `_finally` | `continuation_keywords` (`false` is `same_line`) |
| `dotnet_sort_system_directives_first` | `using_order` (`true` is `system_first`) |
| `csharp_style_namespace_declarations` | `namespace_style` (`file_scoped`, `block_scoped`) |
| `csharp_prefer_braces` | `braces` (`true` is `always`, `when_multiline` is `single_line_only`, `false` is `preserve`) |
| `csharp_preferred_modifier_order` | `modifier_order` |

Roslyn severities such as `true:warning` are read as their value. `root = true`
stops the search, and the file nearest the source wins.

## Defaults

### Whitespace and files

| Setting | Default | Alternatives |
| --- | --- | --- |
| `indent_style` | `space` | `tab` |
| `indent_size` | `4` | any integer |
| `max_line_length` | `120` | any integer, `0` for no limit |
| `end_of_line` | `preserve` | `lf`, `crlf` |
| `charset` | `preserve` (keeps an existing BOM) | `utf-8`, `utf-8-bom` |
| `insert_final_newline` | `true` | `false` |
| `trim_trailing_whitespace` | `true`: formatted lines never end in whitespace. Accepted for `.editorconfig` compatibility; text printed as written keeps its own. | `false` |
| `lang_version` | `auto`: read `LangVersion`, or the oldest target framework, from the nearest `.csproj` and `Directory.Build.props`; loose files assume the latest C# | `latest`, or a version such as `9` or `12` |

### Braces and continuation keywords

| Setting | Default | Alternatives |
| --- | --- | --- |
| `brace_style` | `allman` | `kr`, `mixed` (Allman for types and members, K&R in method bodies) |
| `continuation_keywords` | `blank_line`: `else`, `else if`, `catch`, `finally`, and a `do` loop's `while` go on their own line after a blank line | `new_line`, `same_line` |
| `braces` | `preserve` | `always`, `single_line_only` |
| `empty_bodies` | `inline`: `{ }` on the declaration line, or on its own line when the header spans lines | `allman` |

Short auto-property accessors always stay on one line: `public int Id { get; set; }`.

Property patterns stay inline when they fit. When broken across lines,
their opening brace follows `brace_style` for statements.

```csharp
if (order.IsPaid)
{
    Send(order);
}

else
{
    Hold(order);
}

do
{
    item = queue.Dequeue();
}

while (item != null);
```

### Blank lines

| Setting | Default | Alternatives |
| --- | --- | --- |
| `member_blank_lines` | `group_fields`: consecutive fields and auto-properties stay tight, one blank line around methods, constructors, and other members with bodies | `all`, `preserve` |
| `blank_lines_around_blocks` | `true`: a block statement gets a blank line before and after it, except right after `{` or right before `}` | `false` |
| `max_blank_lines` | `1`: author's blank lines between plain statements are kept, runs collapse to one | any integer, `0` |
| `directive_blank_lines` | `remove`: no blank line directly above or below `#if`, `#elif`, `#else` and `#endif` | `preserve` |

No blank line ever follows `{` or precedes `}`. A comment directly above a block moves with
it, so the blank line goes above the comment.

```csharp
public void Ship()
{
    var order = Load();

    // Bail out early
    if (order == null)
    {
        return;
    }

    foreach (var line in order.Lines)
    {
        Reserve(line);
    }

    Send(order);
}
```

### Line breaking

`for` headers keep a space after each semicolon even when the next clause
is omitted: `for (var i = 0; ;)`. There is no space before the closing
parenthesis unless all three clauses are empty: `for (; ; )`.

| Setting | Default | Alternatives |
| --- | --- | --- |
| `argument_wrap` | `one_per_line`: each argument on its own line, `)` on its own line. Also applies to parameter lists. | `one_per_line_close_on_last`, `fill`, `align` |
| `chain_break_threshold` | `2`: a chain of 2 or more method calls always breaks before each `.`, regardless of length. Property access does not count and stays on the receiver line. | any integer, `0` to break only past `max_line_length` |
| `expression_body_chain` | `own_line`: a broken chain after `=>` moves to the next line | `hang` |
| `binary_wrap` | `before_operator_paren_own_line` | `before_operator`, `after_operator` |
| `ternary_wrap` | `before`: break before `?` and `:` when too long | `after`, `always` |
| `lambda_body` | `hug`: the last argument hangs off the call line when it is a lambda with a block body or a broken member chain, or a creation with a broken initializer | `argument` |

`binary_wrap` also controls line breaks in `or` and `and` patterns.
With `before_operator_paren_own_line`, broken conditions in catch
filters, `if`, `while`, and `do` loops put the expression below `(` and `)`
on its own line, including predicate calls and mixed Boolean/pattern
conditions. Pattern operators take one further continuation indent.
Negated pattern chains and trailing Boolean operators share one continuation
indent, including `value is not A and not B && condition`.

```csharp
var invoice = invoiceService.CreateInvoice(
    customer.Id,
    order.Lines,
    DateTime.UtcNow,
    billingAddress,
    shippingAddress
);

var total = order.Lines
    .Where(l => l.IsTaxable)
    .Sum(l => l.Amount);

public int PaidCount =>
    Orders
        .Where(o => o.IsPaid)
        .Count();

if (
    order.IsPaid
    && order.Lines.Count > 0
    && customer.IsActive
)
{
    Send(order);
}

var shipping = order.Total > FreeShippingThreshold
    ? 0m
    : CalculateShipping(order.Weight, order.Destination, order.Carrier);

orders.ForEach(order =>
{
    Validate(order);
    Send(order);
});
```

### Initializers and collections

| Setting | Default | Alternatives |
| --- | --- | --- |
| `initializer_break_threshold` | `2`: object initializers, anonymous types, and lists of complex items break at 2 or more members | any integer, `0` to break only past `max_line_length` |
| `simple_lists_inline` | `true`: lists of literals, constants, and plain names stay on one line when they fit | `false` |
| `trailing_commas` | `remove` | `add`, `preserve` |

Inline collection expressions keep their brackets tight, including complex
elements: `[new Item()]`. Broken collections put the elements on new lines.
When a collection starts on an argument's own line, its opening bracket
does not add another line break.

```csharp
var empty = new Order { Id = 42 };

var point = new Point
{
    X = 1,
    Y = 2
};

var primes = new List<int> { 2, 3, 5, 7 };

int[] codes = [200, 404];
```

### Alignment

| Setting | Default | Alternatives |
| --- | --- | --- |
| `align_switch_arms` | `false`: one space before each arm's `=>` | `true` |
| `align_assignments` | `false`: one space before each `=` | `true`: consecutive local assignments and field initializers |
| `align_enum_values` | `false`: one space before each `=` | `true` |

By default nothing is padded into columns: alignment shifts whenever one line
changes, and the diff touches every line of the run. Turned on, only the `=`
or `=>` aligns; types and names are not put into columns, and a run ends at a
blank line or at any statement of a different kind:

```csharp
var id       = order.Id;
var customer = order.Customer;

var label = status switch
{
    Status.Paid    => "Paid",
    Status.Pending => "Pending",
    _              => "Unknown"
};

public enum Status
{
    Pending   = 0,
    Paid      = 1,
    Cancelled = 2
}
```

### Switch statements

| Setting | Default | Alternatives |
| --- | --- | --- |
| `switch_case_indent` | `true` | `false` |
| `switch_case_blank_lines` | `true`: blank line between case sections; stacked fall-through labels stay together | `false` |

Comments after the final switch section align with its statements. A switch
containing only comments indents them one level inside its braces.

### Syntax rewrites

These change tokens, not only whitespace. Verification accounts for each one.

| Setting | Default | Alternatives |
| --- | --- | --- |
| `namespace_style` | `file_scoped_if_supported`: file-scoped on C# 10+, block-scoped below | `file_scoped`, `block`, `preserve` |
| `using_order` | `alphabetical`: pure ordinal sort, `System` not pulled first, no group gaps. `using static` then aliases follow the plain directives. | `system_first`, `system_first_grouped`, `preserve` |
| `expression_bodies` | `prefer`: single-expression methods, properties, constructors, and setters become `=>`, including `void` ones. A body containing a comment stays a block. | `block`, `properties_only`, `preserve` |
| `attributes` | `separate`: each attribute on its own line in its own brackets. Parameter attributes stay inline. | `combine`, `preserve` |
| `modifier_order` | `dotnet`: access, `static`, `extern`, `new`, `virtual`, `abstract`, `sealed`, `override`, `readonly`, `unsafe`, `required`, `volatile`, `async` | `preserve` |
| `parentheses` | `remove_obvious`: around a whole `return` value, a lone name or literal, or a whole condition. Precedence-clarifying parentheses stay. | `remove_redundant`, `preserve` |
| `regions` | `preserve` | `remove`, `normalize` |

### Comments

| Setting | Default | Alternatives |
| --- | --- | --- |
| `comment_space` | `true`: `//text` becomes `// text`. `////` and `//---` banners are left alone. | `false` |
| `comment_wrap` | `true`: rewrap long `//` comments to `max_line_length` | `false` |

Comment text is otherwise never changed. Consecutive `//` lines form a
paragraph, which is printed as written unless one of its lines would pass the
line width; only then are its words rewrapped. A comment is not rewrapped when
it looks like commented-out code (ends in `;`, `{`, or `}`, or contains `=>`),
contains a URL, is a list line (`- `, `* `, `1. `), is indented text (two or
more spaces after `//`), or is a `TODO:` line in a multi-line block. XML doc
comments (`///`) and block comments are only reindented.

A comment that stood on its own line stays on its own line. A comment after
code stays after that code: any code that would follow it on the line moves
to the next line instead.

## Printed as written

Some code is printed exactly as it stands, so formatting cannot misplace it:

- string and character literals of every kind, interpolated strings included;
- preprocessor directive lines, at column 0 when they were written there;
- a statement or member that holds a preprocessor directive in the middle of
  an expression, such as a `#pragma` between two switch arms;
- code under `// prettycsharp-ignore` comments (below).

## Skipping files and regions

On by default:

- `bin/`, `obj/`, hidden folders, `*.g.cs`, `*.g.i.cs`, `*.Designer.cs`,
  `*.generated.cs`, and files marked `<auto-generated` in their opening comments
- Paths matched by `.gitignore` inside a git repository (`respect_gitignore = true`)
- Paths matched by `.prettycsharpignore` files at or above a file, gitignore syntax
- `// prettycsharp-ignore` leaves the next statement or member untouched
- `// prettycsharp-ignore-start` through `// prettycsharp-ignore-end` leaves a range untouched

`--no-ignore` turns off both ignore files for one run.

## Conditional compilation

tree-sitter's C# grammar parses every `#if` branch as code. When the
branches together are valid C#, the file is formatted as a whole. When they
are not, because a declaration or statement is split between branches, the
file is formatted one view at a time (`conditional.py`):

1. A view is a set of defined symbols. Conditions are evaluated as the
   compiler does (`!`, `&&`, `||`, `==`, `!=`, parentheses, `true`, `false`),
   with `#define` and `#undef` honoured where they are compiled.
2. In a view, each directive line and each run of inactive lines is replaced
   by a placeholder comment. What is left is the code the compiler sees, and
   it is formatted normally, verification included. The placeholders then go
   back to the text they stood for, exactly as written.
3. Views are tried simplest first (no symbols, each symbol alone, all, all
   but one, at most 16) and kept when they parse and make a branch active
   that no earlier view did, so every branch is formatted in its own view.
4. The result is checked through every view used: with the same lines set
   aside, it must be the same code as the source. Otherwise the file is left
   untouched.

In this mode no rewrite moves code across a directive: the namespace style
is left as it is, a using never moves past a directive, modifiers split by
one keep their order, and a comma with hidden lines between it and the
closing brace is not taken for a trailing comma.

With `syntax_errors = "format_around"` (below), a view that does not parse
is still used when hiding its fewest unreadable lines makes it parse: the
view is formatted around those lines, and the final check hides the same
lines, found by their text, in the view of the source and of the result.

## Code the parser cannot read

| Setting | Default | Alternatives |
| --- | --- | --- |
| `syntax_errors` | `skip_file`: a file that does not parse is reported and left untouched | `format_around` |

The parser supports assignments to the contextual identifier `required`
and C# 14 null-conditional member and element assignments. For these two
grammar gaps, a compatibility pass uses same-width lexical stand-ins,
requires a complete error-free parse, and restores the original tokens and
conditional-access syntax before printing and verification. Invalid input
is still refused; the canonical verifier is unchanged.

Other syntax newer than the grammar, such as the `#:` directives of
file-based apps, does not parse. With
`format_around`, the formatter looks for the fewest whole lines whose removal
lets the file parse (`isolate.py`), trying the lines around each error in
turn. Those lines are hidden behind placeholder comments, the rest is
formatted and verified, and they go back exactly as written, moved to the
indentation their placeholder was printed at (unless they could hold a
multi-line string). Each hidden line must sit between the same two code
tokens before and after formatting, so the order of the code cannot change.
The command line names the lines left as written.

No more than half a file's lines are hidden, and some code must be left to
format; otherwise the file is skipped as before.

## Limits

A file still is not formatted when no view of its `#if` branches parses and,
with `format_around`, hiding lines makes neither a view nor the whole file
parse. Lines are hidden whole, so a one-line member that holds unreadable
syntax is kept as written in full.
