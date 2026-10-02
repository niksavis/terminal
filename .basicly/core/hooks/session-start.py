from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

CLI_TIMEOUT_S = 10.0

NO_TRACKER_PREFIX = "ledger: none"

HOOK_OUTPUT_CAP = 10_000
CUT_NOTICE = "\n[cut at the {cap}-character hook cap: run `basicly session start` for the rest]"


def cli_command() -> list[str] | None:

    found = shutil.which("basicly")
    if found:
        return [found, "session", "start"]
    if importlib.util.find_spec("basicly") is not None:
        return [sys.executable, "-m", "basicly.cli", "session", "start"]
    return None


def orientation() -> str | None:
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
    return within_cap(report)


def within_cap(report: str) -> str:

    if len(report) <= HOOK_OUTPUT_CAP:
        return report
    notice = CUT_NOTICE.format(cap=HOOK_OUTPUT_CAP)
    return report[: HOOK_OUTPUT_CAP - len(notice)] + notice


def _skipped(reason: str) -> None:
    print(f"session-start: orientation skipped, {reason}", file=sys.stderr)


def wants_json_output(payload: dict) -> bool:

    return bool(payload) and "hook_event_name" not in payload


def main() -> int:
    payload: dict = {}
    report: str | None = None
    try:
        parsed = json.loads(sys.stdin.read() or "{}")
        payload = parsed if isinstance(parsed, dict) else {}
        report = orientation()
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
