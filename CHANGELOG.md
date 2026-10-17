# Changelog

Each release's section becomes the body of its GitHub release.

## [Unreleased]

- Parsing with tree-sitter-c-sharp. A file with a syntax error is reported
  with its line and column and left untouched.
- The `prettycsharp` command with `format`, `check` and `diff`, their
  `--write`, `--check` and `--diff` aliases, and stdout output for one file.
  Line endings and a UTF-8 byte order mark are kept as the file has them.
- No layout rules yet: every valid file comes back unchanged. DESIGN.md
  holds the planned defaults.
