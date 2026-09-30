from __future__ import annotations

import importlib.util
import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

LEDGER = Path(".basicly") / "ledger"
PLACES = ((Path(".basicly") / "core" / "kit" / "tracker" / "cli.py").as_posix(),)
LOCATE = Path(__file__).resolve().parent.parent / "kit" / "tracker" / "locate.py"


def _locate() -> Any:
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_locate", LOCATE)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's locate.py is missing at {LOCATE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["basicly_tracker_kit_locate"] = module
    spec.loader.exec_module(module)
    return module


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
    if not paths or not (root / LEDGER).is_dir():
        return 0
    if _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        return 0
    locate = _locate()
    tracker = locate.locate(root, PLACES)
    if tracker is None:
        sys.stderr.write(f"tracker-claim: {locate.missing(root, LEDGER.as_posix(), PLACES)}\n")
        return 1
    staged = _git(root, "diff", "--cached", "--name-only").stdout
    check = ["commit-check", str(LEDGER), paths[0], "--stdin", "--runner", tracker.typed()]
    done = subprocess.run(  # nosec B603
        [*tracker.argv(sys.executable), *check],
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
