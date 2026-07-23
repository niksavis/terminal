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


def _project_root() -> Path:
    """Repo root: git runs hooks with cwd at the top of the working tree.

    Never derived from this file's location — the managed core may be
    relocated via ``basicly.toml [paths]``. Walking up covers direct
    invocation from a subdirectory.
    """
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


# Beads issue ids look like <prefix>-<short-code>, e.g. "basicly-idr" or
# "br-a1b2c3", with optional dotted child levels ("basicly-zrj.4.1"). br's own
# commit scanner (``br orphans``) matches ids prefix-anchored by word boundary
# anywhere in the message, so ordinary hyphenated words are never ids. We mirror
# that shape below instead of a loose ``word-word`` regex, which mis-flagged
# phrases like "fork-drove-the-loop" as unknown ids (basicly-jms0).
def _candidate_ids(message: str, known_ids: set[str]) -> set[str]:
    """Return the issue-id tokens in *message*, restricted to known prefixes.

    The prefix set is derived from *known_ids* (no extra config), so detection
    tracks whatever prefixes the workspace actually uses and matches br's own
    prefix-anchored scanner.
    """
    prefixes = {pid.split("-", 1)[0] for pid in known_ids if "-" in pid}
    if not prefixes:
        return set()
    alternation = "|".join(re.escape(prefix) for prefix in sorted(prefixes))
    pattern = re.compile(rf"\b(?:{alternation})-[a-z0-9]+(?:\.[0-9]+)*\b")
    return set(pattern.findall(message))


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


def _beads_dir() -> Path:
    """The active beads dir, following br's git-ignored ``redirect`` file.

    A harness worktree shares the base checkout's tracker via a one-line
    ``.beads/redirect`` (written at provisioning); a fresh id then only exists
    in the redirected JSONL, so the hook must read the same dir ``br`` does.
    """
    beads = _project_root() / ".beads"
    redirect = beads / "redirect"
    if redirect.is_file():
        try:
            target = Path(redirect.read_text(encoding="utf-8").strip())
        except OSError:
            return beads
        if target.is_dir():
            return target
    return beads


def _load_known_issue_ids() -> set[str] | None:
    """Return the set of known issue ids, or None if no beads workspace exists."""
    issues_jsonl = _beads_dir() / "issues.jsonl"
    if not issues_jsonl.exists():
        return None

    known_ids: set[str] = set()
    for raw_line in issues_jsonl.read_text(encoding="utf-8").splitlines():
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

    candidates = _candidate_ids(message, known_ids)
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
