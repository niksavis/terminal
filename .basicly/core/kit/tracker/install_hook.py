from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

HOOK_NAME = "post-merge"

GIT_DIR_NAME = ".git"
_GIT_DIR_MARK = "gitdir:"
DEFAULT_HOOKS_DIR = "hooks"
HOOKS_PATH_KEY = "hookspath"

DEFAULT_INTERPRETER = "uv run --no-project --no-python-downloads python"

BEGIN = "# >>> basicly-tracker compact >>>"
END = "# <<< basicly-tracker compact <<<"

SHEBANG = "#!/bin/sh"

CLI_FILE = "cli.py"

_HERE = Path(__file__).resolve().parent


def _within(path: Path, root: Path) -> str:

    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path(root).resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"{resolved} is not inside {root}, so no relative command can be written and "
            f"an absolute one would break the next clone"
        ) from exc


def git_dir(root: Path) -> Path | None:

    candidate = root / GIT_DIR_NAME
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text.startswith(_GIT_DIR_MARK):
            linked = Path(text[len(_GIT_DIR_MARK) :].strip())
            return linked if linked.is_absolute() else (root / linked).resolve()
    return None


def hooks_dir(root: Path) -> Path | None:

    found = git_dir(root)
    if found is None:
        return None
    config = found / "config"
    declared = ""
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip().lower() == HOOKS_PATH_KEY:
                declared = value.strip()
    if not declared:
        return found / DEFAULT_HOOKS_DIR
    path = Path(declared)
    return path if path.is_absolute() else (root / path)


def body(interpreter: str, script: str, ledger: str) -> str:

    return "\n".join((
        BEGIN,
        f'if [ -f "{script}" ] && [ -z "$(git status --porcelain -- . ":(exclude){ledger}")" ]',
        "then",
        f'  {interpreter} "{script}" compact "{ledger}" >/dev/null 2>&1 || exit 0',
        f'  if [ -n "$(git status --porcelain -- "{ledger}")" ]; then',
        f'    git add "{ledger}" >/dev/null 2>&1',
        '    git commit -q -m "chore(tracker): fold pending shards into the trunk log" \\',
        "      >/dev/null 2>&1 ||",
        '      echo "tracker: folded the shards but could not commit them; the ledger is'
        ' staged and your tree is not clean" >&2',
        "  fi",
        "fi",
        END,
    ))


def _stripped(text: str) -> str:

    kept = []
    inside = False
    for line in text.splitlines():
        if line.strip() == BEGIN:
            inside = True
            continue
        if line.strip() == END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept).rstrip("\n")


def merged(current: str, block: str) -> str:

    if not current.strip():
        return f"{SHEBANG}\n\n{block}\n"
    kept = _stripped(current)
    if not kept.splitlines() or not kept.splitlines()[0].startswith("#!"):
        kept = f"{SHEBANG}\n{kept}"
    return f"{kept.rstrip()}\n\n{block}\n"


def _make_executable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    except OSError:
        pass


def install(root: Path, *, ledger: Path, dry_run: bool, interpreter: str, stream: Any) -> int:

    script = _within(_HERE / CLI_FILE, root)
    within = _within(ledger, root)
    directory = hooks_dir(root)
    if directory is None:
        stream.write(
            f"tracker: {root} is not a git checkout, so there is no {HOOK_NAME} to wire; "
            f"run `compact` yourself after a merge\n"
        )
        return 0
    hook = directory / HOOK_NAME
    current = hook.read_text(encoding="utf-8") if hook.is_file() else ""
    wanted = merged(current, body(interpreter, script, within))
    if current == wanted:
        stream.write(f"tracker: {HOOK_NAME} already folds shards after a merge\n")
        return 0
    if dry_run:
        stream.write(f"tracker: would write {HOOK_NAME} in {directory}\n")
        return 0
    directory.mkdir(parents=True, exist_ok=True)
    hook.write_text(wanted, encoding="utf-8")
    _make_executable(hook)
    kept = bool(_stripped(current).strip())
    how = "added the compact block to the existing" if kept else "wrote"
    stream.write(f"tracker: {how} {HOOK_NAME} in {directory}\n")
    return 0


def uninstall(root: Path, *, dry_run: bool, stream: Any) -> int:

    directory = hooks_dir(root)
    hook = directory / HOOK_NAME if directory is not None else None
    if hook is None or not hook.is_file():
        return 0
    current = hook.read_text(encoding="utf-8")
    if BEGIN not in current:
        stream.write(f"tracker: {HOOK_NAME} carries no block this kit wrote, so it is left alone\n")
        return 0
    if dry_run:
        stream.write(f"tracker: would remove the compact block from {HOOK_NAME}\n")
        return 0
    kept = _stripped(current).strip()
    if kept in ("", SHEBANG):
        hook.unlink()
        stream.write(f"tracker: removed {HOOK_NAME}, which held nothing else\n")
        return 0
    hook.write_text(f"{kept}\n", encoding="utf-8")
    stream.write(f"tracker: removed the compact block from {HOOK_NAME}\n")
    return 0


def main(argv: Any = None) -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Wire a post-merge hook that folds every pending writer shard into the "
            "trunk log, so a consumer never has to remember `compact`."
        )
    )
    parser.add_argument("--root", default=".", help="the repository to wire")
    parser.add_argument(
        "--ledger",
        default="",
        help="the ledger directory the hook compacts; defaults beside the vendored kit",
    )
    parser.add_argument(
        "--uninstall", action="store_true", help="remove only the block this writes"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would change and write nothing"
    )
    parser.add_argument(
        "--interpreter",
        default=DEFAULT_INTERPRETER,
        help="the command that runs the kit; the default needs only uv",
    )
    args = parser.parse_args(None if argv is None else list(argv))
    root = Path(args.root).resolve()
    if args.uninstall:
        return uninstall(root, dry_run=args.dry_run, stream=sys.stdout)
    ledger = Path(args.ledger) if args.ledger else _HERE.parent.parent / "ledger"
    if not ledger.is_absolute():
        ledger = root / ledger
    return install(
        root,
        ledger=ledger,
        dry_run=args.dry_run,
        interpreter=args.interpreter,
        stream=sys.stdout,
    )


if __name__ == "__main__":
    sys.exit(main())
