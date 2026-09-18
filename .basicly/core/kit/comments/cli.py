from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent

SKIPPED_DIRECTORIES = frozenset({
    ".bzr",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "obj",
    "target",
    "vendor",
    "venv",
})


def _load(file_name: str, module_name: str):
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the comments kit's " + file_name + " is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


languages = _load("languages.py", "basicly_comments_kit_languages")
scan = _load("scan.py", "basicly_comments_kit_scan")
strip = _load("strip.py", "basicly_comments_kit_strip")


def covered_files(roots, skipped) -> list:
    found = []
    for root in roots:
        path = Path(root)
        if path.is_file():
            if scan.is_covered(path) and not any(part in skipped for part in path.parts):
                found.append(path)
            continue
        for candidate in sorted(path.rglob("*")):
            if not candidate.is_file() or not scan.is_covered(candidate):
                continue
            if any(part in skipped for part in candidate.parts):
                continue
            found.append(candidate)
    return found


def check(paths, stream) -> int:
    found = unreadable = 0
    for path in paths:
        try:
            for finding in scan.findings(path, path.read_text(encoding="utf-8")):
                stream.write(f"{path}:{finding.line}: {_one_line(finding.text)}\n")
                found += 1
        except (scan.LexError, UnicodeDecodeError) as err:
            stream.write(f"{path}: cannot be read with certainty, so it is left alone: {err}\n")
            unreadable += 1
    stream.write(
        f"comments: {found} prose comments in {len(paths)} files, {unreadable} unreadable\n"
    )
    if unreadable:
        return 2
    return 1 if found else 0


def fix(paths, stream) -> int:
    changed = refused = 0
    for path in paths:
        try:
            source = path.read_text(encoding="utf-8")
            stripped = strip.strip_source(path, source)
        except (scan.LexError, strip.UnsafeStripError, UnicodeDecodeError) as err:
            stream.write(f"{path}: refused, nothing written: {err}\n")
            refused += 1
            continue
        if stripped != source:
            path.write_text(stripped, encoding="utf-8", newline="\n")
            changed += 1
    stream.write(f"comments: rewrote {changed} of {len(paths)} files, refused {refused}\n")
    return 2 if refused else 0


def _one_line(text: str) -> str:
    first = text.strip().split("\n")[0]
    return first if len(first) <= 88 else first[:85] + "..."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="basicly-comments",
        description="Refuse prose comments in code, and remove them when asked.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("check", "report every prose comment and exit 1 when one is found"),
        ("fix", "remove every prose comment, leaving the directives a tool reads"),
    ):
        sub = subcommands.add_parser(name, help=help_text)
        sub.add_argument("paths", nargs="*", default=["."], help="files or directories")
        sub.add_argument(
            "--skip",
            action="append",
            default=[],
            metavar="NAME",
            help="a directory name to skip, in addition to the built-in list",
        )
    subcommands.add_parser("languages", help="print every file extension the kit claims")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "languages":
        for suffix in languages.covered_suffixes():
            sys.stdout.write(suffix + "\n")
        return 0
    paths = covered_files(args.paths or ["."], SKIPPED_DIRECTORIES | set(args.skip))
    if args.command == "check":
        return check(paths, sys.stdout)
    return fix(paths, sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
