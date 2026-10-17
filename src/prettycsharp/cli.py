"""The prettycsharp command line.

    prettycsharp format PATH...   rewrite files in place     (alias --write)
    prettycsharp check PATH...    exit 1 if any would change (alias --check)
    prettycsharp diff PATH...     print a unified diff        (alias --diff)
    prettycsharp PATH             print the formatted file to stdout
    prettycsharp -                format stdin to stdout

A PATH is a .cs file, a folder, a .csproj, or a .sln or .slnx. Exit status:
0 when nothing needs to change, 1 when check or diff found a file that
would change, 2 when a file could not be read, parsed or formatted, or the
settings are wrong.
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

from prettycsharp import __version__, config, ignore, project
from prettycsharp.config import settings_for
from prettycsharp.formatter import FormattingError, format_source
from prettycsharp.ignore import Ignorer
from prettycsharp.parsing import CSharpSyntaxError
from prettycsharp.project import compiled_files, lang_version_for, solution_projects
from prettycsharp.settings import Settings, SettingsError

_BOM = chr(0xFEFF)
_MODES = {"format": "write", "check": "check", "diff": "diff"}


class _Options:
    def __init__(self, namespace: argparse.Namespace) -> None:
        self.overrides: dict[str, object] = {}
        for item in namespace.option or []:
            key, sep, value = item.partition("=")
            if not sep or not key.strip():
                raise SettingsError(f"--option {item!r}: use KEY=VALUE")
            self.overrides[key.strip()] = value.strip()
        self.config: Path | None = namespace.config
        self.no_ignore: bool = namespace.no_ignore
        self.ignorer = Ignorer(respect_gitignore=not self.no_ignore, use_ignore_files=not self.no_ignore)
        self.stdin_filepath: Path | None = namespace.stdin_filepath

    def ignorer_for(self, target: Path) -> Ignorer:
        """The skipping rules for a target, honouring its respect_gitignore setting."""
        if self.no_ignore:
            return self.ignorer
        probe = target / "probe.cs" if target.is_dir() else target
        settings = settings_for(probe, self.overrides, self.config)
        return Ignorer(respect_gitignore=settings.respect_gitignore, use_ignore_files=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    # Settings, project and ignore files are cached for one run, not across runs.
    config.clear_caches()
    project.clear_caches()
    ignore.clear_caches()
    mode = "stdout"
    if args and args[0] in _MODES:
        mode = _MODES[args.pop(0)]

    parser = argparse.ArgumentParser(prog="prettycsharp", description="Format C# source files.")
    parser.add_argument("paths", nargs="+", help=".cs files, folders, .csproj or .sln files, or - for stdin")
    parser.add_argument("--version", action="version", version=f"prettycsharp {__version__}")
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument("--write", action="store_const", const="write", dest="mode", help="same as format")
    flags.add_argument("--check", action="store_const", const="check", dest="mode", help="same as check")
    flags.add_argument("--diff", action="store_const", const="diff", dest="mode", help="same as diff")
    parser.add_argument("--config", type=Path, help="use this settings file instead of searching for one")
    parser.add_argument(
        "-o", "--option", action="append", metavar="KEY=VALUE", help="set one setting, over every settings file"
    )
    parser.add_argument("--no-ignore", action="store_true", help="do not skip files .gitignore or .prettycsharpignore lists")
    parser.add_argument("--stdin-filepath", type=Path, help="the path stdin stands for, to find its settings")
    namespace = parser.parse_args(args)
    if namespace.mode is not None:
        if mode != "stdout" and namespace.mode != mode:
            parser.error("give a subcommand or a flag, not two different ones")
        mode = namespace.mode

    try:
        options = _Options(namespace)
        if namespace.config is not None and not namespace.config.is_file():
            raise SettingsError(f"--config {namespace.config}: no such file")
    except SettingsError as error:
        print(f"prettycsharp: {error}", file=sys.stderr)
        return 2

    if namespace.paths == ["-"]:
        return _run_stdin(options)
    if "-" in namespace.paths:
        parser.error("- (stdin) cannot be combined with other paths")

    files, status = _collect(namespace.paths, options)
    if mode == "stdout" and len(files) != 1:
        if status:
            return status
        parser.error("printing to stdout takes exactly one file; use format, check or diff")
    for path in files:
        status = max(status, _run(path, mode, options))
    return status


def _collect(targets: Sequence[str], options: _Options) -> tuple[list[Path], int]:
    files: list[Path] = []
    seen: set[Path] = set()
    status = 0
    for target in targets:
        path = Path(target)
        if not path.exists():
            print(f"{path}: no such file or folder", file=sys.stderr)
            status = 2
            continue
        try:
            ignorer = options.ignorer_for(path)
        except SettingsError as error:
            print(f"prettycsharp: {error}", file=sys.stderr)
            status = 2
            continue
        for found in _expand(path, ignorer):
            key = found.resolve()
            if key not in seen:
                seen.add(key)
                files.append(found)
    return files, status


def _expand(path: Path, ignorer: Ignorer) -> Iterator[Path]:
    suffix = path.suffix.lower()
    if path.is_dir():
        for folder, subfolders, names in os.walk(path):
            here = Path(folder)
            subfolders[:] = sorted(s for s in subfolders if not ignorer.skip_folder(here / s))
            for name in sorted(names):
                candidate = here / name
                if name.lower().endswith(".cs") and not ignorer.skip_file(candidate):
                    yield candidate
    elif suffix == ".csproj":
        for found in compiled_files(path):
            if not ignorer.skip_file(found):
                yield found
    elif suffix in (".sln", ".slnx"):
        for project in solution_projects(path):
            if project.is_file():
                yield from _expand(project, ignorer)
    elif not ignorer.skip_file(path):
        yield path


def _settings(path: Path, options: _Options) -> Settings:
    return settings_for(path, options.overrides, options.config)


def _format_text(text: str, path: Path, settings: Settings) -> str:
    """Format text read from ``path``, keeping or changing its byte order mark."""
    bom = _BOM if text.startswith(_BOM) else ""
    lang = lang_version_for(path) if settings.lang_version == "auto" else None
    formatted = format_source(text[len(bom) :], settings, lang_version=lang)
    if settings.charset == "utf-8-bom":
        bom = _BOM
    elif settings.charset == "utf-8":
        bom = ""
    return bom + formatted


def _run_stdin(options: _Options) -> int:
    path = options.stdin_filepath or Path("stdin.cs")
    text = sys.stdin.read()
    if options.stdin_filepath is not None and options.ignorer.skip_file(path):
        sys.stdout.write(text)
        return 0
    try:
        formatted = _format_text(text, path, _settings(path, options))
    except (CSharpSyntaxError, FormattingError, SettingsError) as error:
        print(f"{path}: {error}; not formatted", file=sys.stderr)
        return 2
    sys.stdout.write(formatted.lstrip(_BOM))
    return 0


def _run(path: Path, mode: str, options: _Options) -> int:
    try:
        settings = _settings(path, options)
    except SettingsError as error:
        print(f"prettycsharp: {error}", file=sys.stderr)
        return 2
    try:
        # newline="" keeps the file's own line endings.
        with path.open(encoding="utf-8", newline="") as handle:
            original = handle.read()
    except (OSError, UnicodeDecodeError) as error:
        print(f"{path}: cannot read: {error}", file=sys.stderr)
        return 2

    try:
        formatted = _format_text(original, path, settings)
    except CSharpSyntaxError as error:
        print(f"{path}: {error}; not formatted", file=sys.stderr)
        return 2
    except FormattingError as error:
        print(f"{path}: not formatted: {error}", file=sys.stderr)
        return 2

    if mode == "stdout":
        sys.stdout.write(formatted.lstrip(_BOM))
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
