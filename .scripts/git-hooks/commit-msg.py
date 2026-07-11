"""Validate conventional commit message format.

Installed as a commit-msg hook via pre-commit.
Usage: python .scripts/commit_msg_format.py <commit-msg-file>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

MIN_DESCRIPTION_LENGTH = 3


ALLOWED_TYPES = (
    "feat",
    "fix",
    "docs",
    "style",
    "refactor",
    "perf",
    "test",
    "build",
    "ci",
    "chore",
    "revert",
)

# type(scope): description
# Scope is optional and lowercase-kebab-case.
# Description starts with lowercase and is at least 3 chars.
_MIN_DESC = MIN_DESCRIPTION_LENGTH - 1
PATTERN = re.compile(
    r"^(" + "|".join(ALLOWED_TYPES) + r")(\([a-z0-9-]+\))?: [a-z].{" + str(_MIN_DESC) + r",}$"
)

ERROR_MESSAGE = """ERROR: Commit message does not follow conventional commit format.

Expected format: type(scope): description

Allowed types:
  feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert

Examples:
  feat(basicly): add fragment loader
  fix: correct sorting order in planner
  docs: update architecture decision record
"""


def validate(message: str) -> bool:
    """Return True if the commit message matches conventional commit format."""
    first_line = message.splitlines()[0] if message else ""
    # Ignore merge commits and revert commits with long auto-generated bodies.
    if first_line.startswith(("Merge ", 'Revert "')):
        return True
    return bool(PATTERN.match(first_line))


def main() -> int:
    """Entry point for the commit-msg hook."""
    if len(sys.argv) < 2:
        print("Usage: commit-msg.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    message = commit_msg_file.read_text(encoding="utf-8").strip()

    if validate(message):
        print("Commit message format is valid.")
        return 0

    print(ERROR_MESSAGE, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
