# Changelog

Each release's section becomes the body of its GitHub release.

## [1.1.6] - 2026-10-18

- `for` headers keep a space between semicolons when the condition is
  omitted, such as `for (var start = 0; ;)`, avoiding Visual Studio's
  IDE0055 formatting diagnostic. Fully empty headers print `for (; ; )`.

## [1.1.5] - 2026-10-18

- Nullable array types print tight, `object?[]?`, instead of
  `object? []?`, and spread elements are spaced, `[.. items]`, as Visual
  Studio formats them (IDE0055). Ranges such as `items[..2]` stay tight.
- An empty collection `[]` is never split across lines. When it does not
  fit, the line breaks after `=>` or `=` and `[]` goes to the next line.
- No blank line is left directly above or below `#if`, `#elif`, `#else`
  and `#endif`. A comment above an `#if` keeps the blank line above the
  comment. The new setting `directive_blank_lines = "preserve"` keeps the
  blank lines as written.

## [1.1.4] - 2026-10-17

- An empty body `{ }` after a header that spans lines goes on its own line,
  as Visual Studio formats it. Before, `) { }` after a broken parameter
  list, constructor initializer, `where` clause, base list, catch filter or
  lambda parameter list was flagged by IDE0055. A header on one line keeps
  `{ }` beside it.

## [1.1.3] - 2026-10-17

- A property's accessor list or an enum that holds only a comment no longer
  gains a blank line each time the file is formatted. Found by fuzzing.

## [1.1.2] - 2026-10-17

- Nothing is padded into columns by default any more: `align_assignments`,
  `align_enum_values` and `align_switch_arms` now default to `false`, so each
  `=` and `=>` has one space before it. Padded columns shift whenever one
  line changes, and the diff then touches every line of the run. Set any of
  the three to `true` to align as before.

## [1.1.1] - 2026-10-17

- `syntax_errors = "format_around"` now works inside each view of a file
  split by `#if`: a view that does not parse is formatted around its own
  unreadable lines, so both branches of a split class header are formatted
  even when a method holds syntax newer than the parser. Before, the
  fallback ran on the whole file and kept the branch lines as written.
- A comma followed only by hidden `#if` lines before the closing brace is no
  longer removed as a trailing comma, since in another view it separates
  items. Files like this were skipped before; on ten open-source
  repositories the default settings now skip 11 files instead of 14, and
  `format_around` skips 2.

## [1.1.0] - 2026-10-17

- Files whose `#if` branches split a declaration or statement, such as a
  class header with a different base list in each branch, are formatted
  instead of refused. Each view of the file (a set of defined symbols) is
  formatted on its own with the other branches set aside, so every branch
  is formatted, and the result is checked through every view. On ten
  open-source repositories this formats 94 of the 108 files that 1.0.0
  skipped.
- A file that ends in a directive without a final line break, such as
  `#pragma warning restore`, parses.
- A new setting, `syntax_errors = "format_around"`, formats files that hold
  syntax newer than the parser, such as C# 14's null-conditional assignment
  or the `#:` directives of file-based apps. The fewest lines the parser
  cannot read are left as written, moved to the new indentation, and the
  rest is formatted; the command line names the lines it kept. The default,
  `skip_file`, leaves such files untouched as before.
- `format_details()` returns the formatted text with the lines left as
  written.

## [1.0.0] - 2026-10-17

The first release: a complete formatter for C# files, projects and
solutions.

- A Prettier-style layout engine prints every C# construct: Allman braces,
  4-space indentation and a 120-column line, with calls, parameter lists,
  conditions, ternaries, member chains, initializers, switch statements and
  expressions, lambdas, queries and patterns breaking only where needed.
- The defaults in DESIGN.md: a blank line before `else`, `catch`,
  `finally` and a do loop's `while`; blank lines around block statements;
  fields grouped tight and members with bodies apart; member chains of two
  or more calls broken one call per line; initializers of two or more
  members broken; aligned `=` in runs of assignments, field initializers and
  enum values, and aligned switch-expression arms.
- Rewrites that change tokens, each one checked: file-scoped namespaces
  from C# 10, sorted usings, the .NET modifier order, expression-bodied
  members, one attribute per list, removal of obvious parentheses and of
  trailing commas.
- Every setting in DESIGN.md can be changed, from `.prettycsharp.toml`,
  `[tool.prettycsharp]` in `pyproject.toml`, `.editorconfig`, or `-o` on the
  command line. Unknown settings and bad values are errors.
- The C# version for namespace style and expression bodies comes from the
  project's `LangVersion` or target framework.
- Targets can be files, folders, `.csproj`, `.sln` and `.slnx` files, or
  stdin. `bin/`, `obj/`, generated files and paths in `.gitignore` or
  `.prettycsharpignore` are skipped, and `// prettycsharp-ignore` comments
  leave code as written.
- Every output is parsed again and compared with the input as syntax trees
  and comment words. A file that would change in meaning, or that does not
  parse, is reported and left untouched. Line endings and a byte order mark
  are kept, and files are written through a temporary file.
- Comments stay where they were written: a comment on its own line stays on
  its own line, and a comment after code stays after that code. Long `//`
  paragraphs are rewrapped to the line width.
