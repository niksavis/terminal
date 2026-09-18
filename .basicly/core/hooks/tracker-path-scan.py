from __future__ import annotations

import getpass
import json
import re
import subprocess  # nosec B404
import sys

_TRACKER_GLOB = re.compile(r"^\.basicly/ledger/events-.*\.jsonl$")

_PATH_TAIL = r"[^\s\"'`,;)\]}]*"

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("posix-home-path", re.compile(rf"/(?:home|Users)/[A-Za-z0-9._-]+{_PATH_TAIL}")),
    ("windows-unc-path", re.compile(rf"\\\\\?\\[A-Za-z]:\\{_PATH_TAIL}")),
    ("windows-drive-path", re.compile(rf"[A-Za-z]:\\{_PATH_TAIL}")),
)

_IDENTITY_RULE = "machine-username"
_MIN_IDENTITY_LENGTH = 4


def identity_pattern() -> re.Pattern[str] | None:

    try:
        name = getpass.getuser()
    except KeyError, OSError:
        return None
    if len(name) < _MIN_IDENTITY_LENGTH:
        return None
    return re.compile(rf"\b{re.escape(name)}\b")


def staged_tracker_files() -> list[str]:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if _TRACKER_GLOB.match(line)]


def staged_content(path: str) -> str:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "show", f":{path}"], capture_output=True, text=True, check=False
    )
    return proc.stdout if proc.returncode == 0 else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def rule_hit(texts: list[str], identity: re.Pattern[str] | None = None) -> str | None:
    for rule, pattern in _RULES:
        if any(pattern.search(text) for text in texts):
            return rule
    if identity is not None and any(identity.search(text) for text in texts):
        return _IDENTITY_RULE
    return None


def findings(path: str, content: str) -> list[tuple[str, int, str]]:
    identity = identity_pattern()
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            texts = _strings(json.loads(line))
        except json.JSONDecodeError:
            texts = [line]
        if rule := rule_hit(texts, identity):
            hits.append((path, lineno, rule))
    return hits


def main() -> int:
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
        "Repair it with:  basicly tracker scrub\n"
        "(prefix that with `uv run` or with your `uvx --from <pin>` when basicly is not "
        "on PATH), then re-stage .basicly/ledger.\n"
        "A harness loop advance repairs it automatically.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
