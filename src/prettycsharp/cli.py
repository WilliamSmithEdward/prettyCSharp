"""The prettycsharp command line.

    prettycsharp format PATH...   rewrite files in place   (alias --write)
    prettycsharp check PATH...    exit 1 if any would change (alias --check)
    prettycsharp diff PATH...     print a unified diff      (alias --diff)
    prettycsharp PATH             print the formatted file to stdout

A PATH is a .cs file or a folder, searched for .cs files outside bin/, obj/
and hidden folders. Exit status: 0 when nothing needs to change, 1 when
check or diff found a file that would change, 2 when a file could not be
read or parsed.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator, Sequence
from pathlib import Path

from prettycsharp import __version__
from prettycsharp.formatter import format_source
from prettycsharp.parsing import CSharpSyntaxError

_BOM = chr(0xFEFF)
_SKIPPED_FOLDERS = {"bin", "obj"}
_MODES = {"format": "write", "check": "check", "diff": "diff"}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = "stdout"
    if args and args[0] in _MODES:
        mode = _MODES[args.pop(0)]

    parser = argparse.ArgumentParser(prog="prettycsharp", description="Format C# source files.")
    parser.add_argument("paths", nargs="+", type=Path, help=".cs files or folders")
    parser.add_argument("--version", action="version", version=f"prettycsharp {__version__}")
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--write", action="store_const", const="write", dest="mode")
    flags.add_argument("--check", action="store_const", const="check", dest="mode")
    flags.add_argument("--diff", action="store_const", const="diff", dest="mode")
    options = parser.parse_args(args)
    if options.mode is not None:
        if mode != "stdout" and options.mode != mode:
            parser.error("give a subcommand or a flag, not two different ones")
        mode = options.mode

    files = list(_source_files(options.paths))
    if mode == "stdout" and len(files) != 1:
        parser.error("printing to stdout takes exactly one file; use format, check or diff")

    status = 0
    for path in files:
        status = max(status, _run(path, mode))
    return status


def _source_files(paths: Sequence[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            for found in sorted(path.rglob("*.cs")):
                parts = found.relative_to(path).parts[:-1]
                if not any(part in _SKIPPED_FOLDERS or part.startswith(".") for part in parts):
                    yield found
        else:
            yield path


def _run(path: Path, mode: str) -> int:
    try:
        # newline="" keeps the file's own line endings, as DESIGN.md asks.
        with path.open(encoding="utf-8", newline="") as handle:
            original = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        print(f"{path}: cannot read: {error}", file=sys.stderr)
        return 2

    bom = _BOM if original.startswith(_BOM) else ""
    try:
        formatted = bom + format_source(original[len(bom) :])
    except CSharpSyntaxError as error:
        print(f"{path}: {error}; not formatted", file=sys.stderr)
        return 2

    if mode == "stdout":
        sys.stdout.write(formatted[len(bom) :])
        return 0
    if formatted == original:
        return 0
    if mode == "write":
        try:
            _replace(path, formatted)
        except OSError as error:
            print(f"{path}: cannot write: {error}", file=sys.stderr)
            return 2
        print(f"formatted {path}")
        return 0
    if mode == "diff":
        sys.stdout.writelines(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                formatted.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
        )
    else:
        print(f"would format {path}")
    return 1


def _replace(path: Path, text: str) -> None:
    # Write beside the file, then swap it in, so a failed write never leaves
    # the original half-written. The new file keeps the original's mode.
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
