from __future__ import annotations

import json
import subprocess  # nosec B404
import sys
from pathlib import Path

LEDGER = Path(".basicly") / "ledger"
KIT_CLIS = (
    Path(".basicly") / "core" / "kit" / "tracker" / "cli.py",
    Path(".basicly") / "kit" / "tracker" / "cli.py",
)


def _project_root() -> Path:
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )


def main(argv: list[str] | None = None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    root = _project_root()
    cli = next((root / candidate for candidate in KIT_CLIS if (root / candidate).is_file()), None)
    if not paths or cli is None or not (root / LEDGER).is_dir():
        return 0
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return 0
    staged = _git(root, "diff", "--cached", "--name-only").stdout
    done = subprocess.run(  # nosec B603
        [sys.executable, str(cli), "commit-check", str(LEDGER), paths[0], "--stdin"],
        input=staged,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode == 0:
        return 0
    try:
        refused = json.loads(done.stdout).get("refused") or done.stdout
    except ValueError:
        refused = done.stdout + done.stderr
    sys.stderr.write(f"tracker-claim: {refused}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
