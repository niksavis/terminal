from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

DIST_REPO = "git+https://github.com/niksavis/basicly"
DIST_FALLBACK = f"{DIST_REPO}@main"
INSTALL_STATE = Path(".basicly/state/install.json")


def dist_source(repo_root: Path | None = None) -> str:

    state = (repo_root or Path.cwd()) / INSTALL_STATE
    try:
        version = json.loads(state.read_text(encoding="utf-8"))["basicly_version"]
    except OSError, ValueError, KeyError, TypeError:
        return DIST_FALLBACK
    return f"{DIST_REPO}@v{version}" if isinstance(version, str) and version else DIST_FALLBACK


def _cli_command() -> list[str] | None:
    basicly = shutil.which("basicly")
    if basicly:
        return [basicly, "catalog", "lint"]
    if importlib.util.find_spec("basicly") is not None:
        return [sys.executable, "-m", "basicly.cli", "catalog", "lint"]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", dist_source(), "basicly", "catalog", "lint"]
    return None


UNRESOLVABLE = ("couldn't find remote ref", "failed to fetch branch or tag")

SKIPPED = (
    "catalog-lint skipped: no basicly to lint with ({reason}); "
    "CI (basicly-gates.yml) runs this check as the deterministic backstop."
)


def main() -> int:
    command = _cli_command()
    if command is None:
        print(
            SKIPPED.format(reason="not installed and uvx is unavailable"),
            file=sys.stderr,
        )
        return 0
    proc = subprocess.run(  # nosec B603
        command, cwd=Path.cwd(), check=False, capture_output=True, text=True
    )
    if proc.returncode != 0 and any(word in proc.stderr for word in UNRESOLVABLE):
        print(SKIPPED.format(reason=f"{dist_source()} does not resolve"), file=sys.stderr)
        return 0
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
