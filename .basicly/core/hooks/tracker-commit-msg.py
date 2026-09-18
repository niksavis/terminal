from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _project_root() -> Path:

    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _candidate_ids(message: str, known_ids: set[str]) -> set[str]:

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

LEDGER_DIR = Path(".basicly") / "ledger"
LEDGER_GLOBS = ("events-*.jsonl", "pending-*.jsonl")


def _tracker_root() -> Path:

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

    ledger_dir = _tracker_root() / LEDGER_DIR
    ledger_ids: set[str] = set()
    for log in sorted(f for glob in LEDGER_GLOBS for f in ledger_dir.glob(glob)):
        ledger_ids |= _ids_from_jsonl(log, "record")
    if ledger_ids:
        return ledger_ids, " or ".join(str(LEDGER_DIR / glob) for glob in LEDGER_GLOBS)
    return None


def _load_known_issue_ids() -> set[str] | None:
    found = _known_ids_with_source()
    return None if found is None else found[0]


def validate(
    message: str, known_ids: set[str] | None, source: str = "the tracker"
) -> tuple[bool, str]:

    first_line = message.splitlines()[0] if message else ""
    if first_line.startswith(("Merge ", 'Revert "')):
        return True, ""

    if known_ids is None:
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
