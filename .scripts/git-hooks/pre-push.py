from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_CHECK = ".scripts/bundle_cli_tools_skill.py"


def in_ci(environ: dict[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get("CI", "")
    return value.strip().lower() not in {"", "0", "false", "no"}


def _bundle_check() -> int:
    print("==> cli-tools bundle check")
    return subprocess.run(  # nosec
        ["uv", "run", "python", BUNDLE_CHECK, "--check"], cwd=PROJECT_ROOT, check=False
    ).returncode


def _pytest() -> int:
    print("==> pytest (whole suite)")
    start = time.perf_counter()
    result = subprocess.run(["uv", "run", "pytest", "tests/"], cwd=PROJECT_ROOT, check=False)  # nosec
    print(f"pytest finished in {time.perf_counter() - start:.2f}s")
    return result.returncode


def main() -> int:
    if _bundle_check() != 0:
        print("pre-push failed: the cli-tools bundle check", file=sys.stderr)
        return 1
    if not in_ci():
        print("pre-push: local push, so no tests run here; CI runs the whole suite")
        return 0
    if _pytest() != 0:
        print("pre-push failed: pytest", file=sys.stderr)
        return 1
    print("pre-push passed in CI: bundle check, pytest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
