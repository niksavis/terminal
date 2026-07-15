"""Validate conventional commit message format.

Installed as a commit-msg hook via pre-commit.
Usage: python .basicly/core/hooks/commit-msg.py <commit-msg-file>
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

# type(scope)!: description (optional-issue-id[, issue-id...])
# Scope is optional and lowercase-kebab-case. An optional "!" before the colon
# marks a breaking change per the Conventional Commits spec.
# Description must be entirely lowercase (not just the first letter; proper
# nouns and acronyms get lowercased too), allows letters/digits/space/hyphen
# only (no underscores or other punctuation), has at least
# MIN_DESCRIPTION_LENGTH chars, and must not end with punctuation.
# An optional trailing parenthetical referencing one or more beads (br) issue
# ids is permitted syntactically here; beads-commit-msg.py validates that the
# referenced id(s) actually exist. A beads id is a kebab-case prefix plus a
# hyphenated base, with optional dotted hierarchy levels (e.g. basicly-q49,
# basicly-zrj.8, basicly-zrj.4.1) — the dots must be accepted here to match
# beads' own id scheme.
ISSUE_ID = r"[a-z][a-z0-9]*-[a-z0-9]+(?:\.[a-z0-9]+)*"
HEADER_PATTERN = re.compile(
    r"^(" + "|".join(ALLOWED_TYPES) + r")(\([a-z0-9]+(?:-[a-z0-9]+)*\))?(!)?: "
    r"(.+?)(?:\s+\((" + ISSUE_ID + r"(?:,\s*" + ISSUE_ID + r")*)\))?$"
)
DESCRIPTION_PATTERN = re.compile(r"^[a-z][a-z0-9 -]*[a-z0-9]$")

ERROR_MESSAGE = """ERROR: Commit message does not follow conventional commit format.

Expected format: type(scope)!: description

Rules:
    - type must be one of the allowed types below
    - scope is optional and must be lowercase-kebab-case
    - an optional "!" before the colon marks a breaking change
    - description must be entirely lowercase (proper nouns/acronyms included)
    - description allows only letters, digits, spaces, and hyphens (no underscores)
    - description must be at least 3 characters
    - description cannot end with punctuation

Allowed types:
  feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert

Examples:
  feat(basicly): add fragment loader
  fix: correct sorting order in planner
  docs: update architecture decision record
  feat(basicly): add fragment loader (basicly-idr)
  feat(basicly)!: remove deprecated config format

Invalid examples:
    chote(word description): message;
    chore(word description): message
    chore(scope): Message
"""


def validate(message: str) -> bool:
    """Return True if the commit message matches conventional commit format."""
    first_line = message.splitlines()[0] if message else ""
    # Ignore merge commits and revert commits with long auto-generated bodies.
    if first_line.startswith(("Merge ", 'Revert "')):
        return True

    header_match = HEADER_PATTERN.match(first_line)
    if not header_match:
        return False

    description = header_match.group(4)
    if len(description) < MIN_DESCRIPTION_LENGTH:
        return False

    return bool(DESCRIPTION_PATTERN.fullmatch(description))


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
