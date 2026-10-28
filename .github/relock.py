"""Relock what a Dependabot pull request changed, the way the locks are built.

The same in every repository; the canonical copy lives in
WilliamSmithEdward/repo-standards (templates/relock). Dependabot recompiles
uv's hash-locked requirement files with its own pip-compile, which drops
setuptools, pip and the platform markers, and rewrites a multi-framework
packages.lock.json for one target framework only. Either way CI fails and
the update never merges. relock-dependabot.yml runs this on a Dependabot
branch and pushes whatever it changes.

For each changed lock file that records a `uv pip compile` command on its
second line, the file starts again from the base branch's copy and that
command runs with `--upgrade-package name==version` for every package whose
pinned version the pull request moved, so the moves Dependabot meant are
kept and nothing else changes. If any packages.lock.json, project file or
Directory.Packages.props changed, `dotnet restore --force-evaluate` runs on
the repository's solution.

Usage: python relock.py <base-ref>     (from the repository root)
Prints one line per file it rebuilt; exits non-zero on a failed command.
"""
import re
import shlex
import subprocess
import sys
from pathlib import Path

PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;\\]+)", re.M)
DOTNET_INPUTS = ("packages.lock.json", ".csproj", "Directory.Packages.props")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def pins(text):
    return {m.group(1).lower().replace("_", "-"): m.group(2) for m in PIN.finditer(text)}


def uv_command(text):
    lines = text.splitlines()
    if len(lines) < 2:
        return None
    command = lines[1].lstrip("#").strip()
    return shlex.split(command) if command.startswith("uv pip compile ") else None


def relock_requirements(base, path):
    head = Path(path).read_text(encoding="utf-8")
    command = uv_command(head)
    if command is None:
        return False
    try:
        old = git("show", f"{base}:{path}")
    except subprocess.CalledProcessError:
        return False  # a new lock file: nothing to start again from
    moved = [f"{name}=={version}" for name, version in pins(head).items()
             if pins(old).get(name) not in (None, version)]
    Path(path).write_text(old, encoding="utf-8", newline="\n")
    upgrades = [arg for spec in moved for arg in ("--upgrade-package", spec)]
    subprocess.run(command + upgrades + ["--quiet"], cwd=Path(path).parent, check=True)
    print(f"relocked {path}" + (f" ({', '.join(moved)})" if moved else ""))
    return True


def solution():
    found = sorted(Path(".").glob("*.sln")) + sorted(Path(".").glob("*.slnx"))
    return str(found[0]) if found else None


def main():
    base = sys.argv[1]
    changed = git("diff", "--name-only", f"{base}...HEAD").split()
    for path in changed:
        if path.endswith(".txt") and Path(path).is_file():
            relock_requirements(base, path)
    if any(path.endswith(DOTNET_INPUTS) for path in changed):
        sln = solution()
        if sln:
            subprocess.run(["dotnet", "restore", sln, "--force-evaluate"], check=True)
            print(f"restored {sln} with --force-evaluate")


if __name__ == "__main__":
    main()
