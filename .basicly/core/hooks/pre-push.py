"""Run all pre-push checks.

This script is invoked by the pre-push hook (via pre-commit or lefthook).
It runs the test suite and any other checks that should block a push.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    """Entry point for the pre-push hook."""
    print("==> pytest")
    start = time.perf_counter()
    result = subprocess.run(
        ["uv", "run", "pytest", "tests/"],
        cwd=PROJECT_ROOT,
        check=False,
    )  # nosec
    elapsed = time.perf_counter() - start

    if result.returncode == 0:
        print(f"pre-push passed in {elapsed:.2f}s")
    else:
        print(f"pre-push failed in {elapsed:.2f}s", file=sys.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
