"""Validate that a commit message references a known beads (br) issue id.

Installed as a second commit-msg hook via pre-commit, run alongside
commit-msg.py. Kept standalone (single responsibility: conventional format vs.
beads-id presence) so either check can be added, removed, or reused
independently by pre-commit, lefthook, or another hook manager.

Usage: python .basicly/core/hooks/beads-commit-msg.py <commit-msg-file>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BEADS_DIR = PROJECT_ROOT / ".beads"
ISSUES_JSONL = BEADS_DIR / "issues.jsonl"

# Beads issue ids look like <prefix>-<short-code>, e.g. "basicly-idr" or
# "br-a1b2c3". Prefix and code are both lowercase alnum.
ISSUE_ID_PATTERN = re.compile(r"\b[a-z][a-z0-9]*-[a-z0-9]+\b")

NO_ID_MESSAGE = """ERROR: Commit message does not reference a beads issue id.

This repo requires every commit to reference a tracked beads (br) issue.

Reference an id as a parenthetical after the description, e.g.:
  feat(basicly): add fragment loader (basicly-idr)

Create an issue first if one doesn't exist yet:
  br create "Title" --type task --priority 2
  br q "Quick capture title"
"""

UNKNOWN_ID_MESSAGE_TEMPLATE = """ERROR: Commit message references an unknown beads issue id: {ids}

None of the referenced id(s) were found in .beads/issues.jsonl.

Check valid ids with:
  br list --json
  br show <id>
"""


def _load_known_issue_ids() -> set[str] | None:
    """Return the set of known issue ids, or None if no beads workspace exists."""
    if not ISSUES_JSONL.exists():
        return None

    known_ids: set[str] = set()
    for raw_line in ISSUES_JSONL.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        issue_id = record.get("id")
        if isinstance(issue_id, str):
            known_ids.add(issue_id)
    return known_ids


def validate(message: str, known_ids: set[str] | None) -> tuple[bool, str]:
    """Return (is_valid, error_message) for the given commit message."""
    first_line = message.splitlines()[0] if message else ""
    # Ignore merge commits and revert commits with long auto-generated bodies.
    if first_line.startswith(("Merge ", 'Revert "')):
        return True, ""

    if known_ids is None:
        # No beads workspace in this repo (no .beads/issues.jsonl) — nothing to
        # validate against, so skip entirely; a beads-less consumer must be able
        # to commit without an issue id. Enable tracking with `br init`.
        return True, ""

    candidates = set(ISSUE_ID_PATTERN.findall(message))
    if not candidates:
        return False, NO_ID_MESSAGE

    matched_ids = candidates & known_ids
    if not matched_ids:
        return False, UNKNOWN_ID_MESSAGE_TEMPLATE.format(ids=", ".join(sorted(candidates)))

    return True, ""


def main() -> int:
    """Entry point for the beads commit-msg hook."""
    if len(sys.argv) < 2:
        print("Usage: beads-commit-msg.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    message = commit_msg_file.read_text(encoding="utf-8").strip()

    known_ids = _load_known_issue_ids()
    is_valid, error_message = validate(message, known_ids)

    if is_valid:
        print("Beads issue id reference is valid.")
        return 0

    print(error_message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
