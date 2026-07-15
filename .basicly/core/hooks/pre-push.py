"""Run the configured full checks before a push.

Invoked by the pre-push hook (via pre-commit or lefthook). Runs the
``[[verify.checks]]`` declared for mode ``full`` in the repo's basicly.toml —
the same deterministic gate the harness loop's verify phase uses, so a push is
held to exactly what the repo configures (and nothing it doesn't have).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import run_checks

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    """Entry point for the pre-push hook."""
    return run_checks(PROJECT_ROOT, "full")


if __name__ == "__main__":
    sys.exit(main())
