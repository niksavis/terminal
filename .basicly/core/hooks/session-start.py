"""Put the ledger's orientation in an agent's context at session open (basicly-yru8eu).

Fired by Claude Code (``SessionStart``) and Copilot CLI (``sessionStart``): runs
``basicly session start`` so the orientation arrives before the first turn rather than
when the agent obeys the always-on line or the human asks.

**The hosts read stdout differently** (vendor docs, 2026-08-31): Claude Code adds a
``SessionStart`` hook's *plain-text* stdout to Claude's context
(docs.claude.com/en/docs/claude-code/hooks); Copilot parses stdout as one JSON object and
injects only ``additionalContext`` (docs.github.com/en/copilot/reference/hooks-reference),
dropping plain text unparsed.

Never a gate: every failure prints nothing on stdout and exits 0, reason on stderr — which
Claude Code shows the user and not Claude, so it cannot read as orientation.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

# The bound the hook imposes itself, because a session open waits on it. Measured
# 2026-08-31: 4.2 s over 1187 records, against a 600 s Claude and 30 s Copilot default.
CLI_TIMEOUT_S = 10.0

# `basicly session start`'s first line when the repo has no owned tracker; its later lines
# are not orientation, so the whole report is dropped. `test_session_start_hook` pins it.
NO_TRACKER_PREFIX = "ledger: none"


def cli_command() -> list[str] | None:
    """A runnable ``basicly session start``, or None when the engine is unreachable.

    Without ``catalog-lint.py``'s ``uvx --from <dist>`` rung: installing a distribution
    over the network would blow :data:`CLI_TIMEOUT_S` at session open.
    """
    found = shutil.which("basicly")
    if found:
        return [found, "session", "start"]
    if importlib.util.find_spec("basicly") is not None:
        return [sys.executable, "-m", "basicly.cli", "session", "start"]
    return None


def orientation() -> str | None:
    """The report to inject, or None whenever there is nothing the caller may print."""
    command = cli_command()
    if command is None:
        return None
    try:
        proc = subprocess.run(  # nosec B603 — argv list, no shell, command from PATH
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _skipped(f"`basicly session start` outran {CLI_TIMEOUT_S:g}s")
        return None
    if proc.returncode != 0:
        _skipped(f"`basicly session start` exited {proc.returncode}")
        return None
    report = proc.stdout.strip()
    if not report or report.startswith(NO_TRACKER_PREFIX):
        return None
    return report


def _skipped(reason: str) -> None:
    """Say in one line why no orientation was printed."""
    print(f"session-start: orientation skipped, {reason}", file=sys.stderr)


def wants_json_output(payload: dict) -> bool:
    """Whether the host reading our stdout is Copilot rather than Claude Code.

    Claude Code stamps ``hook_event_name`` on every payload and the camelCase Copilot
    format this projection configures does not — the documented difference between the two
    input shapes. No payload reads as Claude Code, the form a hand run can also read.
    """
    return bool(payload) and "hook_event_name" not in payload


def main() -> int:
    """Print the orientation in the shape the calling host injects. Always exits 0."""
    payload: dict = {}
    report: str | None = None
    try:
        parsed = json.loads(sys.stdin.read() or "{}")
        payload = parsed if isinstance(parsed, dict) else {}
        report = orientation()
    # Narrow by construction: stdin and the spawn raise OSError, the parse ValueError, a
    # killed child SubprocessError. A wider clause would swallow a defect in this file.
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        _skipped(type(exc).__name__)
        return 0
    if report is None:
        return 0
    if wants_json_output(payload):
        print(json.dumps({"additionalContext": report}))
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
