# Notes for coding agents

prettycsharp is a Prettier-style C# formatter in Python: tree-sitter parses
each file and the formatter reprints it in one layout. Read `DESIGN.md`
first; it holds every agreed default and the setting behind it.

The pipeline, in `formatter.py`: `syntax.py` copies tree-sitter's tree into
`Node` objects and attaches comments to tokens; `rewrites.py` makes the
token-changing rewrites; `printer/` turns nodes into a layout document
(`core.py` dispatch, tokens, comments and lists; `expressions.py`,
`statements.py` and `declarations.py` the handlers, each `p_<node type>`);
`doc.py` fits the document to the width; `verify.py` reparses the output and
compares canonical trees. `settings.py`, `config.py`, `project.py`,
`ignore.py` and `cli.py` are the settings, files and command line.

## Commands

```bash
pip install --require-hashes -r .github/requirements/test.txt
pip install --no-deps --no-build-isolation -e .
ruff check src tests fuzz
mypy
python -m pytest
```

## Rules of the road

- A file that does not parse is never rewritten. Do not weaken
  `parsing.parse` to make a test pass.
- The verifier is the safety net: never loosen `verify.canonical` to make
  output pass. A new rewrite gets its own canonical form there, written
  separately from the rewrite, so a bug in one cannot hide in the other.
- Every token goes through `Core.tok`, so its comments are printed; a
  handler that drops a token drops its comments and fails verification.
- Check a printer change against real code before calling it done: format a
  few open-source C# repositories and confirm no file is refused, crashes or
  formats differently a second time.
- The defaults in `DESIGN.md` are the owner's choices. Change one only when
  asked, and update `DESIGN.md` in the same change.
- The package imports the standard library, tree-sitter,
  tree-sitter-c-sharp, defusedxml and (on Python 3.10) tomli, nothing else.
  Other packages are for development.
- A fuzz finding becomes a seed in `tests/fuzz_corpus/csharp` with its fix.
- Keep text in files plain ASCII, apart from test data that is about
  non-ASCII text.

<!-- repo-standards:begin. Copied from WilliamSmithEdward/repo-standards, templates/agents/AGENTS-block.md. Change it there; the weekly rescan fails a copy that differs. -->
## Releases, CI and security

These rules are the same in every WilliamSmithEdward repository.

- **How a release happens here:** pushing a `vX.Y.Z` tag runs Publish, which uploads to PyPI and creates the GitHub release with its security and malware reports.
- **Starting a workflow by hand never releases anything.** Publish and every
  release report are dry runs when started with `gh workflow run` or the Run
  workflow button. They build, scan and assemble the release files exactly
  as a release would, and upload them as the `release-preview` artifact
  instead. Run one after changing anything on the release path:
  `gh workflow run <file> --ref main`, then
  `gh run download <run-id> -n release-preview`.
- **Do not create, publish, edit or delete a release or a `v*` tag** unless
  the owner asks for it. A `v*` tag cannot be moved or deleted once pushed.
- **Every change to `main` goes through a pull request** that passes CI
  passed, Security passed and Malware scan passed. No one can push to `main`
  directly or skip the checks, admins included. Push a branch, open a pull
  request, and let it merge itself: `gh pr merge --auto --squash <number>`.
- **Pins.** Actions by full commit SHA with the version as a comment. Images
  by digest, in `.github/security/<tool>/Dockerfile`. Python tools from the
  hash-locked `.github/requirements/<purpose>.txt`, compiled from the `.in`
  beside it with
  `uv pip compile <purpose>.in --universal --generate-hashes --python-version 3.12 -o <purpose>.txt`.
  Runners are named releases, never `-latest`.
- **Updates merge themselves.** Dependabot and the Update YARA rules workflow
  open pull requests that merge once the three checks pass, except a
  third-party major version, which waits for the owner. Leave them alone
  unless asked.
- **A scanner finding is fixed or accepted with a written reason** in the
  repository's accepted list. Never silence a scanner without one.
<!-- repo-standards:end -->
