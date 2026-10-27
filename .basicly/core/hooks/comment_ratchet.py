from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess  # nosec B404
import sys
from pathlib import Path


class RatchetError(ValueError):
    pass


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(  # nosec B603 B607
            ["git", *args], cwd=root, input=b"", capture_output=True, check=False
        )
    except OSError as err:
        raise RatchetError("Git is unavailable; install Git before running the ratchet") from err


def _read(root: Path, *args: str) -> bytes:
    result = _git(root, *args)
    if result.returncode:
        raise RatchetError("Git cannot read the staged baseline; resolve the index and retry")
    return result.stdout


def _baseline(root: Path) -> str:
    head = _git(root, "rev-parse", "--verify", "HEAD^{tree}")
    if head.returncode == 0:
        return head.stdout.decode("ascii").strip()
    branch = _git(root, "symbolic-ref", "-q", "HEAD")
    if branch.returncode == 0:
        ref = branch.stdout.decode("utf-8").strip()
        exists = _git(root, "show-ref", "--verify", "--quiet", ref)
        if exists.returncode == 1:
            return _read(root, "mktree").decode("ascii").strip()
    raise RatchetError("Git cannot read HEAD; repair the repository before running the ratchet")


def _changed(root: Path, before: str, after: str) -> list:
    fields = _read(
        root,
        "diff",
        "--name-status",
        "--find-renames",
        "--no-ext-diff",
        "--diff-filter=ACMRT",
        "-z",
        before,
        after,
        "--",
    ).split(b"\0")
    changes = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii")
        index += 1
        old = os.fsdecode(fields[index])
        index += 1
        if status.startswith(("R", "C")):
            new = os.fsdecode(fields[index])
            index += 1
        else:
            new = old
        changes.append((status, old, new))
    return changes


def _selected(root: Path, paths: list) -> list:
    selected = []
    for value in paths:
        path = Path(value).absolute()
        try:
            relative = path.relative_to(root)
        except ValueError as err:
            raise RatchetError("ratchet paths must be inside the current Git repository") from err
        selected.append(relative)
    return selected


def check(paths: list, kit) -> int:
    skipped = kit.SKIPPED_DIRECTORIES
    compare = kit._load("ratchet.py", "basicly_comments_kit_ratchet").compare
    current = Path.cwd()
    root = Path(os.fsdecode(_read(current, "rev-parse", "--show-toplevel")).strip()).resolve()
    before = _baseline(root)
    after = _read(root, "write-tree").decode("ascii").strip()
    selected = _selected(root, paths)
    count = files = 0
    for status, old, new in _changed(root, before, after):
        path = Path(new)
        if not kit.scan.is_covered(path) or any(part in skipped for part in path.parts):
            continue
        if not any(value == Path() or path == value or value in path.parents for value in selected):
            continue
        source = _read(root, "show", f"{after}:{new}").decode("utf-8")
        prior = "" if status[0] in "ACT" else _read(root, "show", f"{before}:{old}").decode("utf-8")
        files += 1
        for finding in compare(path, prior, source, Path(old)):
            text = finding.text.strip().split("\n")[0]
            print(f"{path}:{finding.line}: {text}")
            count += 1
    print(f"comments-ratchet: {count} new prose comments in {files} staged files")
    return 1 if count else 0


def main(argv=None, kit_root=None) -> int:
    parser = argparse.ArgumentParser(prog="no-comment-ratchet")
    parser.add_argument("paths", nargs="*", default=["."])
    args = parser.parse_args(argv)
    root = kit_root or Path(__file__).resolve().parent.parent / "kit" / "comments"
    spec = importlib.util.spec_from_file_location("basicly_comments_host_cli", root / "cli.py")
    if spec is None or spec.loader is None:
        raise SystemExit("no-comment-ratchet: comments kit is missing")
    kit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kit)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    try:
        return check(args.paths or ["."], kit)
    except (RatchetError, kit.scan.LexError, UnicodeError, OSError) as err:
        print(f"comments-ratchet: refused: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
