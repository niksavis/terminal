from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

RELEASES = "https://github.com/niksavis/basicly/releases/download"
INSTALL_STATE = Path(".basicly/state/install.json")


def dist_source(repo_root: Path | None = None) -> str:

    state = (repo_root or Path.cwd()) / INSTALL_STATE
    try:
        version = json.loads(state.read_text(encoding="utf-8"))["basicly_version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "catalog-lint cannot read the installed version; rerun the basicly install command"
        ) from exc
    if not isinstance(version, str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise ValueError(
            "catalog-lint installed version is invalid; rerun the basicly install command"
        )
    return f"{RELEASES}/v{version}/basicly-{version}-py3-none-any.whl"


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


SKIPPED = (
    "catalog-lint skipped: no basicly to lint with ({reason}); "
    "CI (basicly-gates.yml) runs this check as the deterministic backstop."
)


def main() -> int:
    try:
        command = _cli_command()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if command is None:
        print(
            SKIPPED.format(reason="not installed and uvx is unavailable"),
            file=sys.stderr,
        )
        return 0
    proc = subprocess.run(  # nosec B603
        command, cwd=Path.cwd(), check=False, capture_output=True, text=True, encoding="utf-8"
    )
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
