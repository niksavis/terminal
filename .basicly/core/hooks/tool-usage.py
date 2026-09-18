from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import (
    tools_in_command,
)

USAGE_DIR = Path(".basicly/usage")
USAGE_FILE = USAGE_DIR / "tool-usage.json"

SHELL_TOOLS = {"bash", "shell"}


def _command_from_payload(payload: dict) -> str | None:
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in SHELL_TOOLS:
        return None
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    if isinstance(args, dict):
        command = args.get("command")
        return command if isinstance(command, str) else None
    return args if isinstance(args, str) else None


def _skill_from_payload(payload: dict) -> str | None:
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() != "skill":
        return None
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    if isinstance(args, dict):
        skill = args.get("skill")
        if isinstance(skill, str) and skill:
            return skill
    return None


def record(tools: list[str], repo_root: Path) -> None:
    if not tools:
        return
    usage_dir = repo_root / USAGE_DIR
    usage_dir.mkdir(parents=True, exist_ok=True)
    gitignore = usage_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")

    usage_file = repo_root / USAGE_FILE
    try:
        stats = json.loads(usage_file.read_text(encoding="utf-8"))
        if not isinstance(stats, dict):
            stats = {}
    except OSError, json.JSONDecodeError:
        stats = {}

    today = datetime.now(UTC).date().isoformat()
    for tool in tools:
        entry = stats.get(tool)
        count = entry.get("count", 0) if isinstance(entry, dict) else 0
        stats[tool] = {"count": count + 1, "last_used": today}

    tmp = usage_file.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(stats, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(usage_file)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        command = _command_from_payload(payload)
        if command:
            record(tools_in_command(command), Path.cwd())
        skill = _skill_from_payload(payload)
        if skill:
            record([f"skill:{skill}"], Path.cwd())
    except Exception as exc:  # noqa: BLE001 — hook boundary, reported below
        print(f"tool-usage: telemetry skipped ({type(exc).__name__})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
