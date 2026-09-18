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

ISSUE_ID = r"[a-z][a-z0-9]*-[a-z0-9]+(?:\.[a-z0-9]+)*"
HEADER_PATTERN = re.compile(
    r"^(" + "|".join(ALLOWED_TYPES) + r")(\([a-z0-9]+(?:-[a-z0-9]+)*\))?(!)?: "
    r"(.+?)(?:\s+\((" + ISSUE_ID + r"(?:,\s*" + ISSUE_ID + r")*)\))?$"
)
DESCRIPTION_PATTERN = re.compile(r"^[a-z][a-z0-9 -]*[a-z0-9]$")
_ALLOWED_DESCRIPTION_CHAR = re.compile(r"[a-z0-9 -]")

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
    first_line = message.splitlines()[0] if message else ""
    if first_line.startswith(("Merge ", 'Revert "')):
        return True

    header_match = HEADER_PATTERN.match(first_line)
    if not header_match:
        return False

    description = header_match.group(4)
    if len(description) < MIN_DESCRIPTION_LENGTH:
        return False

    return bool(DESCRIPTION_PATTERN.fullmatch(description))


def _description_of(message: str) -> str | None:
    first_line = message.splitlines()[0] if message else ""
    match = HEADER_PATTERN.match(first_line)
    return match.group(4) if match else None


def disallowed_description_chars(description: str) -> list[str]:

    bad: list[str] = []
    for char in description:
        if not _ALLOWED_DESCRIPTION_CHAR.fullmatch(char) and char not in bad:
            bad.append(char)
    return bad


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: commit-msg.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    message = commit_msg_file.read_text(encoding="utf-8").strip()

    if validate(message):
        print("Commit message format is valid.")
        return 0

    print(ERROR_MESSAGE, file=sys.stderr)
    description = _description_of(message)
    if description:
        bad = disallowed_description_chars(description)
        if bad:
            rendered = ", ".join(repr(char) for char in bad)
            print(
                f"\nDescription has disallowed character(s): {rendered}. "
                "Use only lowercase letters, digits, spaces, and hyphens; put version "
                "numbers, filenames, and proper-noun capitalization in the commit body.",
                file=sys.stderr,
            )
    return 1


if __name__ == "__main__":
    sys.exit(main())
