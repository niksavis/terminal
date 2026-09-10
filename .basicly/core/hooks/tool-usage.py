"""Count which terminal tools and skills the agent actually invokes (PostToolUse hook).

Fired by Claude Code (``PostToolUse``, matcher ``Bash|Skill``) and GitHub
Copilot (``postToolUse``) after a tool call. Reads the hook JSON from stdin;
for a shell call it extracts the head token of every pipeline segment in the
executed command, and for a Claude ``Skill`` call it records the skill as a
``skill:<name>`` entry. Both increment per-entry counters in
``.basicly/usage/tool-usage.json`` — real data for culling idle tools/skills
from the catalog.

What a shell command *ran* is ``shell_tokens``'s answer, not this module's: the
boundary is recording against parsing. Everything here reads a payload, decides what
is worth counting and writes it down; nothing here looks at shell syntax.

Telemetry, never a gate: every path exits 0, the usage dir ignores itself
(``.basicly/usage/.gitignore``), writes are atomic, and a corrupt counter file
restarts empty instead of failing the agent's tool call.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# The sibling parser, imported the way `kit-boundary.py` imports `check_runner`: a hook
# is run by path under whatever interpreter the host provides, and a test loads it
# through `spec_from_file_location`, so neither puts this directory on `sys.path`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import (
    tools_in_command,
)

USAGE_DIR = Path(".basicly/usage")
USAGE_FILE = USAGE_DIR / "tool-usage.json"

# Tool names that carry a shell command, per platform (Claude: Bash; Copilot:
# bash/shell). Anything else (Edit, view, ...) is not ours to count.
SHELL_TOOLS = {"bash", "shell"}


def _command_from_payload(payload: dict) -> str | None:
    """Return the executed shell command from a Claude or Copilot payload."""
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in SHELL_TOOLS:
        return None
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    if isinstance(args, dict):
        command = args.get("command")
        return command if isinstance(command, str) else None
    return args if isinstance(args, str) else None


def _skill_from_payload(payload: dict) -> str | None:
    """Return the invoked skill name from a Claude ``Skill`` tool payload."""
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
    """Increment counters atomically; a corrupt file restarts empty."""
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
    """Count the payload's tools; telemetry never fails the agent's tool call."""
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
    # A raise here fails a tool call that already succeeded. Narrowing was rejected: the
    # body spans stdin decoding, JSON parsing and two file writes. It reports rather than
    # swallowing — a silent failure is a ledger that quietly stops counting.
    except Exception as exc:  # noqa: BLE001 — hook boundary, reported below
        print(f"tool-usage: telemetry skipped ({type(exc).__name__})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
