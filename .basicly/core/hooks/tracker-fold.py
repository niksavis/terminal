from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8", check=False
    )


def main() -> int:
    root = Path.cwd()
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
    engine = shutil.which("basicly")
    command = (
        ["basicly", "tracker", "fold"] if engine else json.loads(os.environ["BASICLY_FOLD_COMMAND"])
    )
    print(
        f"tracker: pending shards are unchanged; run {shlex.join(command)} outside Git hooks",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
