from __future__ import annotations

import importlib.util
import json
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

CLI_TIMEOUT_S = 10.0

NO_TRACKER_PREFIX = "ledger: none"

HOOK_OUTPUT_CAP = 10_000
CUT_NOTICE = "\n[cut at the {cap}-character hook cap: run `basicly session start` for the rest]"


def _engine_pin() -> Any:
    source = Path(__file__).with_name("engine_pin.py")
    spec = importlib.util.spec_from_file_location("basicly_hook_engine_pin", source)
    if spec is None or spec.loader is None:
        raise ValueError("hook runtime engine_pin.py is missing; rerun the basicly install command")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _repo_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents):
        if (root / ".git").exists():
            return root
    return Path.cwd()


def cli_command() -> list[str] | None:
    return _engine_pin().engine_command(["session", "start"], _repo_root(), uvx_fallback=False)


def orientation() -> str | None:
    command = cli_command()
    if command is None:
        for root in (Path.cwd(), *Path.cwd().parents):
            if (root / ".git").exists():
                script = root / ".basicly/tracker-bootstrap.py"
                command = [sys.executable, str(script)] if script.is_file() else None
                break
    if command is None:
        raise ValueError(
            "run repository tracker bootstrap before implementation; "
            "no tracker runtime is available"
        )
    try:
        proc = subprocess.run(  # nosec B603 — argv list, no shell, command from PATH
            command,
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=CLI_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "tracker startup timed out; restore vault access and "
            "run repository bootstrap before work"
        ) from None
    if proc.returncode != 0:
        raise ValueError(
            "tracker startup refused; run repository bootstrap and resolve its named remedy"
        )
    report = proc.stdout.strip()
    if not report or report.startswith(NO_TRACKER_PREFIX):
        raise ValueError(
            "persistent tracker memory is unavailable; complete repository onboarding before work"
        )
    return within_cap(report)


def within_cap(report: str) -> str:

    if len(report) <= HOOK_OUTPUT_CAP:
        return report
    notice = CUT_NOTICE.format(cap=HOOK_OUTPUT_CAP)
    return report[: HOOK_OUTPUT_CAP - len(notice)] + notice


def _refused(reason: str) -> None:
    print(f"session-start: implementation refused, {reason}", file=sys.stderr)


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
        _refused(str(exc))
        return 2
    if report is None:
        _refused(
            "tracker startup supplied no persistent memory; run repository bootstrap before work"
        )
        return 2
    if wants_json_output(payload):
        print(json.dumps({"additionalContext": report}))
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
