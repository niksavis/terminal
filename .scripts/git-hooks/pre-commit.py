"""Run all pre-commit checks.

This script is invoked by the pre-commit hook (via pre-commit or lefthook).
It exists so the hook logic is testable and portable across hook managers.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def run(name: str, *args: str) -> tuple[int, float]:
    """Run a command and report its result. Return exit code and elapsed seconds."""
    print(f"==> {name}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    start = time.perf_counter()
    result = subprocess.run(
        ["uv", "run", *args],
        cwd=PROJECT_ROOT,
        check=False,
        env=env,
    )  # nosec
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        print(f"FAILED: {name} ({elapsed:.2f}s)", file=sys.stderr)
    return result.returncode, elapsed


def main() -> int:
    """Entry point for the pre-commit hook."""
    checks = [
        ("ruff check", "ruff", "check", "."),
        ("ruff format", "ruff", "format", "--check", "."),
        ("pyright", "pyright", "."),
        (
            "bandit",
            "bandit",
            "-c",
            "pyproject.toml",
            "-r",
            ".scripts",
        ),
        ("markdownlint", "node_modules/.bin/markdownlint-cli2.cmd"),
        ("cheat-sheet-html", "python", ".scripts/render-cheat-sheet.py", "--check"),
    ]

    total_start = time.perf_counter()
    results: list[tuple[str, int, float]] = []
    for name, *args in checks:
        code, elapsed = run(name, *args)
        results.append((name, code, elapsed))

    total_elapsed = time.perf_counter() - total_start
    failed = [name for name, code, _ in results if code != 0]
    passed_count = len(results) - len(failed)

    if failed:
        summary = (
            f"pre-commit failed: {passed_count}/{len(results)} checks passed "
            f"in {total_elapsed:.2f}s"
        )
        print(summary, file=sys.stderr)
        print(f"Failed checks: {', '.join(failed)}", file=sys.stderr)
        return 1

    print(f"pre-commit passed: {len(results)}/{len(results)} checks in {total_elapsed:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
