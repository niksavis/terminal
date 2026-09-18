from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import split_pipeline_segments, strip_heredocs

BLOCK_EXIT_CODE = 2

_BARE_HEAD = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?$")

_ASSIGN_PREFIX = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def command_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in {"bash", "shell"}:
        return ""
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    return (args.get("command") or "") if isinstance(args, dict) else ""


def _assigned_phrases(command: str) -> set[str]:
    names: set[str] = set()
    for match in re.finditer(
        r"(?:^|[\s;&|(])([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|\S*)", command
    ):
        value = match.group(2)
        if value[:1] in {'"', "'"}:
            value = value[1:-1]
        if " " in value or "\t" in value:
            names.add(match.group(1))
    return names


def _head_token(segment: str) -> str:
    for token in segment.strip().split():
        if not _ASSIGN_PREFIX.match(token):
            return token
    return ""


def unsplit_command_vars(command: str) -> tuple[str, ...]:

    phrases = _assigned_phrases(command)
    if not phrases:
        return ()
    found: list[str] = []
    for segment in split_pipeline_segments(strip_heredocs(command)):
        match = _BARE_HEAD.match(_head_token(segment))
        if match and match.group(1) in phrases:
            found.append(match.group(1))
    return tuple(dict.fromkeys(found))


_ADVICE = (
    "zsh does not word-split an unquoted expansion, so the whole value becomes ONE "
    "command name and the call exits 127 while the rest of the chain runs on — a "
    "consumer hit this eight times in a row after reading the rule, which is why this "
    "is a hook and not a note.\n"
    "Use one of:\n"
    "  uv run basicly tracker write -- dep add a b       # write the prefix out\n"
    '  args=(uv run basicly tracker write --); "${args[@]}" dep add a b\n'
    "  alias-free: put the repeated prefix in a shell function, then call the function\n"
    "Then check the command actually ran, not just that the chain returned."
)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    command = command_text(payload)
    if not command:
        return 0
    names = unsplit_command_vars(command)
    if not names:
        return 0
    subject = ", ".join(f"`${name}`" for name in names)
    print(f"bare-var-guard: refusing {subject} in command position: {_ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
