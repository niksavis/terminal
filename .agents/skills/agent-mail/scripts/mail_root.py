from __future__ import annotations

import os
import subprocess  # nosec B404
from pathlib import Path

from mail_store import PROG, RefusedError

FOLDER = ".orchestrator"
MARKER = "agent-mail-root"
MARKER_TEXT = "agent-mail 1\n"
ENV = "ORCH_MAIL_ROOT"


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(  # nosec B603 B607
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    except OSError:
        return None
    except subprocess.TimeoutExpired:
        return None


def git_main_worktree(cwd: Path) -> Path | None:
    result = git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if result is None or result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    return common.parent if common.name == ".git" else None


def marked(folder: Path) -> bool:
    return (folder / MARKER).is_file()


def search_up(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        candidate = folder / FOLDER
        if candidate.is_dir():
            if not marked(candidate):
                raise RefusedError(
                    f"{candidate} exists but has no {MARKER} marker, so it is not a mailbox "
                    f"folder that init made. Run: {PROG} init {folder}"
                )
            return candidate
    return None


def find_root(cwd: Path) -> tuple[Path, str]:
    named = os.environ.get(ENV, "")
    if named:
        root = Path(named).expanduser().resolve()
        if not marked(root):
            raise RefusedError(
                f"{ENV} names {root}, which has no {MARKER} marker. "
                f"Run: {PROG} init <the folder that holds {FOLDER}>"
            )
        return root, f"from {ENV}"
    found = search_up(cwd)
    if found is not None:
        return found, "found above the current folder"
    main = git_main_worktree(cwd)
    if main is not None:
        found = search_up(main)
        if found is not None:
            return found, "found above the main worktree of this repository"
    raise RefusedError(
        f"no mailbox folder found from {cwd}. Run: {PROG} init <the folder that holds all "
        f"agent repositories>, or set {ENV} to an existing {FOLDER} folder"
    )


def cmd_init(cwd: Path, args: list[str]) -> int:
    if len(args) > 1:
        raise RefusedError(f"usage: {PROG} init [folder]")
    base = (cwd / args[0]).resolve() if args else cwd.resolve()
    if not base.is_dir():
        raise RefusedError(f"{base} is not a folder. Run: {PROG} init <an existing folder>")
    root = base / FOLDER
    if root.exists() and not root.is_dir():
        raise RefusedError(f"{root} exists and is not a folder; move it away first")
    changes: list[str] = []
    if not root.is_dir():
        root.mkdir()
        changes.append(f"created {root}")
    for part in ("mail", "locks"):
        if not (root / part).is_dir():
            (root / part).mkdir()
            changes.append(f"created {root / part}")
    if not marked(root):
        with (root / MARKER).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(MARKER_TEXT)
        changes.append(f"wrote the marker {root / MARKER}")
    changes.extend(ignore_root(base, root))
    for change in changes:
        print(change)
    if not changes:
        print(f"nothing changed: {root} is ready")
    print(f"mail root: {root}")
    return 0


def ignore_root(base: Path, root: Path) -> list[str]:
    top = git(base, "rev-parse", "--show-toplevel")
    if top is None:
        return ["git is not available: no ignore file changed"]
    if top.returncode != 0:
        return [f"{base} is not in a git repository: no ignore file changed"]
    toplevel = Path(top.stdout.strip()).resolve()
    probe = (root / MARKER).relative_to(base).as_posix()
    check = git(base, "check-ignore", "-q", "--", probe)
    if check is None or check.returncode not in (0, 1):
        raise RefusedError(f"git check-ignore failed in {base}; no ignore file changed")
    if check.returncode == 0:
        return []
    line = "/" + root.relative_to(toplevel).as_posix() + "/"
    ignore = toplevel / ".gitignore"
    text = ignore.read_text(encoding="utf-8") if ignore.is_file() else ""
    prefix = "" if not text or text.endswith("\n") else "\n"
    with ignore.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{line}\n")
    return [f"added {line} to {ignore}"]
