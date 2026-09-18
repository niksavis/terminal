from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import split_pipeline_segments, strip_heredocs

BLOCK_EXIT_CODE = 2

_TRAP_CLUSTER = re.compile(r"^-[a-qs-zA-Z]*r[a-zA-Z]+$")

_RG_NAMES = frozenset({"rg", "ripgrep"})


def command_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in {"bash", "shell"}:
        return ""
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    return (args.get("command") or "") if isinstance(args, dict) else ""


def swallowed_replacements(command: str) -> tuple[str, ...]:
    found: list[str] = []
    for segment in split_pipeline_segments(strip_heredocs(command)):
        tokens = segment.split()
        index = 0
        while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith("-"):
            index += 1
        if index >= len(tokens) or tokens[index].rsplit("/", maxsplit=1)[-1] not in _RG_NAMES:
            continue
        found.extend(token for token in tokens[index + 1 :] if _TRAP_CLUSTER.match(token))
    return tuple(dict.fromkeys(found))


_ADVICE = (
    "`-r` is `--replace` and takes a value, so the letters after it BECOME the "
    "replacement: the pattern is substituted in every printed line, the line numbers "
    "vanish, and the output still reads as a real finding. Measured here: 92 of 2977 "
    "rg calls did this and only 6 wanted --replace, which is why this is a hook.\n"
    "Ripgrep recurses by default, so drop the r:\n"
    "  rg -n <pattern> <path>        # line numbers, recursive already\n"
    "  rg -l <pattern> <path>        # names only\n"
    "  rg --replace '' <pattern> .   # when you really do want a replacement"
)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    command = command_text(payload)
    if not command:
        return 0
    clusters = swallowed_replacements(command)
    if not clusters:
        return 0
    subject = ", ".join(f"`{cluster}`" for cluster in clusters)
    print(f"rg-replace-guard: refusing {subject}: {_ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
