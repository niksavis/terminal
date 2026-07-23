"""Count which terminal tools and skills the agent actually invokes (PostToolUse hook).

Fired by Claude Code (``PostToolUse``, matcher ``Bash|Skill``) and GitHub
Copilot (``postToolUse``) after a tool call. Reads the hook JSON from stdin;
for a shell call it extracts the head token of every pipeline segment in the
executed command, and for a Claude ``Skill`` call it records the skill as a
``skill:<name>`` entry. Both increment per-entry counters in
``.basicly/usage/tool-usage.json`` — real data for culling idle tools/skills
from the catalog.

Telemetry, never a gate: every path exits 0, the usage dir ignores itself
(``.basicly/usage/.gitignore``), writes are atomic, and a corrupt counter file
restarts empty instead of failing the agent's tool call.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

USAGE_DIR = Path(".basicly/usage")
USAGE_FILE = USAGE_DIR / "tool-usage.json"

# Tool names that carry a shell command, per platform (Claude: Bash; Copilot:
# bash/shell). Anything else (Edit, view, ...) is not ours to count.
SHELL_TOOLS = {"bash", "shell"}

# Segment heads that say nothing about tool selection.
SKIP_TOKENS = {
    "cd",
    "echo",
    "exit",
    "export",
    "set",
    "unset",
    "true",
    "false",
    "then",
    "else",
    "elif",
    "fi",
    "do",
    "done",
    "if",
    "while",
    "until",
    "for",
    "case",
    "esac",
    "{",
    "}",
    "(",
    ")",
}

# Wrappers whose *argument* is the interesting tool (`uv run pytest` counts
# both uv and pytest).
WRAPPER_TOKENS = {"uv", "uvx", "npx", "sudo", "xargs", "command", "exec", "nohup", "time"}

# `cmd <<TAG` / `cmd <<-'TAG'` / `cmd <<\TAG`: everything until the terminator
# line is data, not commands — counting heredoc body lines as tools was
# basicly-587. The optional backslash disables expansion (`<<\EOF`); missing it
# left those bodies unstripped and leaked their keywords/terminator (basicly-v7eu).
_HEREDOC = re.compile(r"<<-?\s*\\?(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1")


def _split_pipeline_segments(command: str) -> list[str]:
    """Split on the pipeline operators ``|| && ; |`` and newlines outside quotes.

    Splitting the raw string with a regex would shatter a quoted argument that
    contains an operator or newline — a multi-line ``git commit -m`` body, a
    ``--title "add x; ship it"`` — into fake segments whose first word is then
    miscounted as a command head (basicly-zcvo). Tracking quote state keeps
    quoted-string contents inside a single segment.
    """
    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        # A backslash escapes the next char everywhere except inside '...'.
        if ch == "\\" and quote != "'" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if command[i : i + 2] in ("||", "&&"):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in (";", "|", "\n"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return segments


def _strip_heredocs(command: str) -> str:
    """Drop here-document bodies so their lines are never counted as tools."""
    out: list[str] = []
    terminator: str | None = None
    for line in command.split("\n"):
        if terminator is not None:
            if line.strip() == terminator:
                terminator = None
            continue
        match = _HEREDOC.search(line)
        if match:
            terminator = match.group("tag")
        out.append(line)
    return "\n".join(out)


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


def tools_in_command(command: str) -> list[str]:
    """Head tokens (basenames) of every pipeline segment, wrappers unwrapped."""
    tools: list[str] = []
    for segment in _split_pipeline_segments(_strip_heredocs(command)):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        while tokens:
            head = tokens[0]
            if "=" in head and not head.startswith("-"):
                tokens.pop(0)  # VAR=val prefix: skip it and keep scanning for the head
                continue
            if head in SKIP_TOKENS or head.startswith("-"):
                tokens = []  # a builtin or a stray flag head names no tool (basicly-v7eu)
            break
        while tokens:
            name = Path(tokens[0]).name
            if not name or not re.match(r"^[A-Za-z0-9._-]+$", name):
                break
            tools.append(name)
            if name in WRAPPER_TOKENS:
                tokens = tokens[1:]
                # `uv run <tool>` / `uv tool run <tool>`: skip subcommand words
                while tokens and tokens[0] in {"run", "tool", "python", "-m"}:
                    if tokens[0] in {"python", "-m"}:
                        tokens = []
                        break
                    tokens = tokens[1:]
                # skip option flags between wrapper and tool
                while tokens and tokens[0].startswith("-"):
                    tokens = tokens[1:]
                continue
            break
    return tools


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
    except Exception:  # nosec B110 — telemetry must never fail the tool call
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
