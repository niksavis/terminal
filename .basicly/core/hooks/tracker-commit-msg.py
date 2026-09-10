"""Validate that a commit message references an issue id the tracker holds.

Installed as a second commit-msg hook via pre-commit, run alongside
commit-msg.py. Kept standalone (single responsibility: conventional format vs.
issue-id presence) so either check can be added, removed, or reused
independently by pre-commit, lefthook, or another hook manager.

**The id set comes from the owned ledger.** This gate never spawned a tracker
binary — it read a store's file — which is why the store it reads could be
changed under it without the gate noticing (basicly-vkh0.42.1).

Usage: python .basicly/core/hooks/tracker-commit-msg.py <commit-msg-file>
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


# Record ids look like <prefix>-<short-code>, e.g. "basicly-idr", with optional
# dotted child levels ("basicly-zrj.4.1"). Matched prefix-anchored by word
# boundary, so ordinary hyphenated words are never ids: a loose ``word-word``
# regex mis-flagged phrases like "fork-drove-the-loop" as unknown (basicly-jms0).
def _candidate_ids(message: str, known_ids: set[str]) -> set[str]:
    """Return the issue-id tokens in *message*, restricted to known prefixes.

    The prefix set is derived from *known_ids* (no extra config), so detection
    tracks whatever prefixes the repository actually uses.
    """
    prefixes = {pid.split("-", 1)[0] for pid in known_ids if "-" in pid}
    if not prefixes:
        return set()
    alternation = "|".join(re.escape(prefix) for prefix in sorted(prefixes))
    pattern = re.compile(rf"\b(?:{alternation})-[a-z0-9]+(?:\.[0-9]+)*\b")
    return set(pattern.findall(message))


NO_ID_MESSAGE = """ERROR: Commit message does not reference a tracked issue id.

This repo requires every commit to reference an issue the tracker holds.

Reference an id as a parenthetical after the description, e.g.:
  feat(basicly): add fragment loader (basicly-idr)

File the issue first if one does not exist yet. The `conventional-commits`
skill covers the message format this gate expects.
"""

UNKNOWN_ID_MESSAGE_TEMPLATE = """ERROR: Commit message references an unknown issue id: {ids}

None of the referenced id(s) were found in {source}.

That file is the id set this gate validates against. An id minted in another
checkout reaches it only once that checkout's tracker state is committed.
"""

REDIRECT_NAME = "redirect"

# The owned ledger, and the one place this hook spells it. The kit owns the glob
# as ``events.LOG_GLOB`` and a hook may not reach into the kit, so the spelling
# is duplicated here on purpose and ``test_tracker_commit_msg`` pins the two
# together — a drifting glob would read every id as unknown and block every
# commit (basicly-vkh0.42.1).
LEDGER_DIR = Path(".basicly") / "ledger"
LEDGER_GLOB = "events-*.jsonl"


def _tracker_root() -> Path:
    """The checkout that owns the tracker: this one, or a redirect target.

    A harness worktree shares the base checkout's ledger via a one-line
    ``redirect`` written at provisioning — one store per repository, never one
    per worktree. Mirrors :func:`basicly.tracker_paths.tracker_root`, which a
    hook may not import, and ``test_tracker_commit_msg`` pins the two together:
    a pre-check owes its gate's answer, so both must resolve alike.
    """
    root = _project_root()
    redirect = root / LEDGER_DIR / REDIRECT_NAME
    if redirect.is_file():
        try:
            target = Path(redirect.read_text(encoding="utf-8").strip())
        except OSError:
            return root
        if target.is_dir():
            return target
    return root


def _ids_from_jsonl(path: Path, key: str) -> set[str]:
    """Every string *key* value in the JSONL at *path*; a bad line is skipped."""
    known_ids: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = record.get(key)
        if isinstance(value, str):
            known_ids.add(value)
    return known_ids


def _known_ids_with_source() -> tuple[set[str], str] | None:
    """The known id set and the file it came from, or None when no tracker exists.

    An **empty** result counts as no source rather than as "no ids": reading an
    empty store as authoritative would report every id as unknown and refuse
    every commit, which is the one failure mode a commit gate must not have.
    """
    ledger_dir = _tracker_root() / LEDGER_DIR
    ledger_ids: set[str] = set()
    for log in sorted(ledger_dir.glob(LEDGER_GLOB)):
        ledger_ids |= _ids_from_jsonl(log, "record")
    if ledger_ids:
        return ledger_ids, str(LEDGER_DIR / LEDGER_GLOB)
    return None


def _load_known_issue_ids() -> set[str] | None:
    """The known id set alone, for a caller that does not report the source."""
    found = _known_ids_with_source()
    return None if found is None else found[0]


def validate(
    message: str, known_ids: set[str] | None, source: str = "the tracker"
) -> tuple[bool, str]:
    """Return (is_valid, error_message) for the given commit message.

    *source* names the file the ids were read from, so an unknown-id refusal
    says which store it checked. It defaults rather than being required because
    the id set and the place it came from are separable, and every caller that
    only has a set should still get the same verdict.
    """
    first_line = message.splitlines()[0] if message else ""
    # Ignore merge commits and revert commits with long auto-generated bodies.
    if first_line.startswith(("Merge ", 'Revert "')):
        return True, ""

    if known_ids is None:
        # No tracker in this repo, so there is nothing to validate against and the
        # check skips entirely. A consumer with no tracker must be able to commit.
        return True, ""

    candidates = _candidate_ids(message, known_ids)
    if not candidates:
        return False, NO_ID_MESSAGE

    matched_ids = candidates & known_ids
    if not matched_ids:
        return False, UNKNOWN_ID_MESSAGE_TEMPLATE.format(
            ids=", ".join(sorted(candidates)), source=source
        )

    return True, ""


def main() -> int:
    """Entry point for the tracker commit-msg hook."""
    if len(sys.argv) < 2:
        print("Usage: tracker-commit-msg.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])
    message = commit_msg_file.read_text(encoding="utf-8").strip()

    found = _known_ids_with_source()
    known_ids, source = (None, "") if found is None else found
    is_valid, error_message = validate(message, known_ids, source or "the tracker")

    if is_valid:
        print("Issue id reference is valid.")
        return 0

    print(error_message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
