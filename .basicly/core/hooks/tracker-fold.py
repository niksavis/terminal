from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
import time
import tomllib
from pathlib import Path
from typing import Any


def _harness(module: Any) -> Any:
    factory = getattr(module, "harness", None)
    if not callable(factory):
        raise ImportError(
            "the tracker kit lacks vault harness support; reinstall with `basicly install --force`"
        )
    return factory()


def _engine_pin() -> Any:
    source = Path(__file__).with_name("engine_pin.py")
    spec = importlib.util.spec_from_file_location("basicly_hook_engine_pin", source)
    if spec is None or spec.loader is None:
        raise ValueError("hook runtime engine_pin.py is missing; rerun the basicly install command")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fold_command(root: Path) -> list[str]:
    found = shutil.which("basicly")
    pinned_command = json.loads(os.environ["BASICLY_FOLD_COMMAND"])
    if not found:
        return pinned_command
    pin = _engine_pin()
    try:
        want = pin.pinned_version(root)
    except ValueError:
        return pinned_command
    if want is None or pin.path_version(found) == want:
        return ["basicly", "tracker", "fold"]
    return pinned_command


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )


def main() -> int:
    root = Path.cwd()
    if not (
        (root / ".basicly-tracker.toml").exists()
        or (root / ".basicly/ledger").is_file()
        or (root / ".basicly/ledger-archive").exists()
    ):
        return _legacy(root)
    source = Path(__file__).resolve().parent.parent / "kit/tracker/locate.py"
    if not source.is_file():
        print(
            "tracker-fold: the tracker kit is missing; reinstall with `basicly install --force`",
            file=sys.stderr,
        )
        return 1
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_locate", source)
    if spec is None or spec.loader is None:
        print("tracker-fold: the tracker kit is missing; reinstall basicly", file=sys.stderr)
        return 1
    module: Any = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        if _harness(module).harness_ledger(root, time.time) is not None:
            return 0
    except (ValueError, OSError, ImportError) as exc:
        print(f"tracker-fold: {exc}", file=sys.stderr)
        return 1
    return _legacy(root)


def _legacy(root: Path) -> int:
    config = root / "basicly.toml"
    if not config.is_file():
        return 0
    settings = tomllib.loads(config.read_text(encoding="utf-8"))
    if not settings.get("tracker", {}).get("fold_on_merge", False):
        return 0
    default = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    branch = default.stdout.strip().removeprefix("origin/")
    branch = branch or git(root, "config", "init.defaultBranch").stdout.strip() or "main"
    current = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    if current.stdout.strip() != branch:
        return 0
    pending = git(root, "rev-list", "--count", "@{u}..HEAD")
    if pending.returncode == 0 and pending.stdout.strip() == "0":
        return 0
    status = git(root, "status", "--porcelain", "--", ".", ":(exclude).basicly/ledger")
    if (
        status.returncode
        or status.stdout.strip()
        or not any((root / ".basicly/ledger").glob("pending-*.jsonl"))
    ):
        return 0
    command = _fold_command(root)
    print(
        f"tracker: pending shards are unchanged; run {shlex.join(command)} outside Git hooks",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
