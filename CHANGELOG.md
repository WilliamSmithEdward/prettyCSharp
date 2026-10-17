# Changelog

Each release's section becomes the body of its GitHub release.

## [Unreleased]

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
