"""Run the configured fast checks before a commit.

Invoked by the pre-commit hook (via pre-commit or lefthook). Runs the
``[[verify.checks]]`` declared for mode ``fast`` in the repo's basicly.toml —
config-driven, so every consumer gates its own stack and a repo with no checks
configured passes with a note (it never fails on tooling it doesn't have).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import run_checks

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    """Entry point for the pre-commit hook."""
    return run_checks(PROJECT_ROOT, "fast")


if __name__ == "__main__":
    sys.exit(main())
