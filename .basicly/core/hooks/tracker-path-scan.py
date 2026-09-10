"""Block a commit that stages a machine-specific path in the tracker export (basicly-vkh0.5).

The tracker export is committed and, for a distribution like this one, cloned by
every consumer — so an absolute path or username in it is published, and it is a
wrong answer on any machine but the one that wrote it. The harness repairs the
log at its own tracker commits (``basicly.br.scrub_ledger``); this is the
deterministic gate that catches whatever that misses: a field a later write adds,
or a log staged by hand before the repair ran.

Design choices, deliberately narrow:

- **Only tracker state.** Absolute paths are legitimate content almost
  everywhere else in a repo — docs, fixtures, this very docstring — so a
  repo-wide path scan would be pure noise. Scoping to the ledger's committed
  ``events-*.jsonl`` is what makes a hit unambiguous: it is committed and it is
  machine-written, which are the two properties that matter.
- **Parsed records, not raw lines.** Scanning the JSON source text would mean
  writing every pattern twice, once per escaping level, and the two copies would
  drift. Parsing each record means one rule set, shared with
  ``src/basicly/redact.py``. A line that will not parse is scanned as raw text
  instead, so a malformed record cannot smuggle a path through.
- **Whole staged file, not added lines only.** Unlike ``secret-scan``, a leak here
  is not confined to what this commit added: the export is machine-written in
  bulk, and a record left over from an earlier commit is just as published.
- **It writes nothing.** A gate that repairs state is not a gate; the repair lives
  in the engine, where it is testable and attributable.
- **stdlib only**, by the hooks convention — no dependency ships to consumers.

The rule set below mirrors ``redact.MACHINE_PATH_RULES``. The hook is a
standalone script copied to consumers, so it cannot import the package — but
``tests/test_tracker_path_scan.py`` asserts the two sets are equal, so this is a
checked mirror rather than a convention. Edit both together.
"""

from __future__ import annotations

import getpass
import json
import re
import subprocess  # nosec B404
import sys

# The committed event log. Its derived folds are deliberately out: they are rebuilt
# from it and git-ignored, so a hit in one is a hit the log already carries. The log
# was outside this glob until basicly-r166, which is why 3,775 of its events published
# a username while the gate above them reported clean.
_TRACKER_GLOB = re.compile(r"^\.basicly/ledger/events-.*\.jsonl$")

# (rule name, pattern) — shapes that identify a location on one machine.
# Matched against parsed strings, so one literal backslash is one backslash.
_PATH_TAIL = r"[^\s\"'`,;)\]}]*"

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("posix-home-path", re.compile(rf"/(?:home|Users)/[A-Za-z0-9._-]+{_PATH_TAIL}")),
    ("windows-unc-path", re.compile(rf"\\\\\?\\[A-Za-z]:\\{_PATH_TAIL}")),
    ("windows-drive-path", re.compile(rf"[A-Za-z]:\\{_PATH_TAIL}")),
)

# Mirrors `redact.IDENTITY_RULE` / `redact.MIN_IDENTITY_LENGTH`. Kept out of _RULES
# because a username is not a shape — only the running machine knows the string, so
# it is built per run rather than declared, and the mirror test compares _RULES alone.
_IDENTITY_RULE = "machine-username"
_MIN_IDENTITY_LENGTH = 4


def identity_pattern() -> re.Pattern[str] | None:
    """A pattern matching this machine's username, or None when there is none to match.

    The committer is the one whose username the export would carry, so reading it
    from the running process needs no configuration and cannot go stale. What it
    cannot catch is a *teammate's* username already in the file — that is the
    `[[privacy.denied]]` list's job, and it is stated rather than implied.
    """
    try:
        name = getpass.getuser()
    except KeyError, OSError:
        return None
    if len(name) < _MIN_IDENTITY_LENGTH:
        return None
    return re.compile(rf"\b{re.escape(name)}\b")


def staged_tracker_files() -> list[str]:
    """Paths of staged tracker JSONL files (added, copied, or modified)."""
    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if _TRACKER_GLOB.match(line)]


def staged_content(path: str) -> str:
    """The staged (index) content of *path*, or "" when it cannot be read."""
    proc = subprocess.run(  # nosec B603 B607
        ["git", "show", f":{path}"], capture_output=True, text=True, check=False
    )
    return proc.stdout if proc.returncode == 0 else ""


def _strings(value: object) -> list[str]:
    """Every string nested anywhere inside *value* (comments, dependency rows …)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def rule_hit(texts: list[str], identity: re.Pattern[str] | None = None) -> str | None:
    """The name of the first rule any string in *texts* trips, or None when clean."""
    for rule, pattern in _RULES:
        if any(pattern.search(text) for text in texts):
            return rule
    if identity is not None and any(identity.search(text) for text in texts):
        return _IDENTITY_RULE
    return None


def findings(path: str, content: str) -> list[tuple[str, int, str]]:
    """(path, line number, rule) for every record carrying a path or this machine's name."""
    identity = identity_pattern()
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            texts = _strings(json.loads(line))
        except json.JSONDecodeError:
            texts = [line]  # unparseable: fall back to the raw text, never skip
        if rule := rule_hit(texts, identity):
            hits.append((path, lineno, rule))
    return hits


def main() -> int:
    """Fail the commit when a staged tracker file carries a machine-specific path."""
    hits = [
        finding
        for path in staged_tracker_files()
        for finding in findings(path, staged_content(path))
    ]
    if not hits:
        return 0
    print(
        "tracker-path-scan: machine-specific path(s) or username in staged tracker "
        "state — commit blocked.",
        file=sys.stderr,
    )
    for path, lineno, rule in hits[:20]:
        print(f"  {path}:{lineno}: {rule}", file=sys.stderr)
    if len(hits) > 20:
        print(f"  … and {len(hits) - 20} more", file=sys.stderr)
    print(
        "The log is committed and cloned by every consumer, so an absolute path or "
        "username in it is published.\n"
        "Repair it with:  uv run python -c "
        '"from pathlib import Path; import basicly.br as b; '
        "print(b.scrub_ledger(Path('.')))\"\n"
        "then re-stage .basicly/ledger. A harness loop advance repairs it "
        "automatically.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
