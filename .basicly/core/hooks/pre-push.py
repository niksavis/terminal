from __future__ import annotations

import importlib.util
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import load_cache, project_root, run_checks
from engine_verify import cache_savings

_EVENTS_SOURCE = Path(__file__).resolve().parent.parent / "kit" / "tracker" / "events.py"

_LEDGER_DIR = Path(".basicly") / "ledger"


def _kit_events() -> Any:

    if not _EVENTS_SOURCE.is_file():
        return None
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_events", _EVENTS_SOURCE)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("basicly_tracker_kit_events", module)
    spec.loader.exec_module(module)
    return module


def ledger_write_in_flight(repo_root: Path) -> bool:
    events = _kit_events()
    if events is None:
        return False
    return events.locking.is_held(repo_root / _LEDGER_DIR / events.LOCK_NAME)


def _unset(sha: str) -> bool:
    return set(sha) == {"0"}


def _git(root: Path, *args: str) -> str | None:
    result = subprocess.run(  # nosec B603, B607 # fixed git argv, no shell
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else None


def pushed_paths(root: Path, refs: str) -> list[str] | None:
    paths: set[str] = set()
    seen = False
    for line in refs.splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        seen = True
        if _unset(parts[1]):
            continue
        local, remote = parts[1], parts[3]
        base = remote if not _unset(remote) else _git(root, "merge-base", local, "origin/HEAD")
        listed = _git(root, "diff", "--name-only", "-z", base.strip(), local) if base else None
        if listed is None:
            return None
        paths.update(path for path in listed.split("\0") if path)
    return sorted(paths) if seen else None


def _local_push(root: Path) -> int:
    changed = pushed_paths(root, os.environ.get("BASICLY_PUSH_REFS") or sys.stdin.read())
    if changed == []:
        print("pre-push: the pushed commits change no file, so no check runs")
        return 0
    scope = "every fast check" if changed is None else f"fast checks for {len(changed)} files"
    print(f"pre-push: {scope}; continuous integration runs the full suite")
    return run_checks(root, "fast", changed=changed)


def main() -> int:
    root = project_root()
    if ledger_write_in_flight(Path(os.environ.get("BASICLY_CHECKOUT") or root)):
        print(
            "pre-push: a ledger write is in flight, so this push would race it.\n"
            "Your commits and unstaged files are unchanged.\n"
            "Wait for the landing to finish, then push again.",
            file=sys.stderr,
        )
        return 1
    if not os.environ.get("CI"):
        return _local_push(root)
    if load_cache(root) and cache_savings(root) > 0:
        result = subprocess.run(  # nosec B603, B607 # fixed project interpreter argv, no shell
            [
                "uv",
                "run",
                "--no-sync",
                "--no-python-downloads",
                "python",
                str(Path(__file__).with_name("engine_verify.py")),
            ],
            cwd=root,
            check=False,
        )
        if result.returncode != 125:
            return result.returncode
        print("pre-push: compatible engine unavailable; running fresh native full checks.")
    return run_checks(root, "full")


if __name__ == "__main__":
    sys.exit(main())
