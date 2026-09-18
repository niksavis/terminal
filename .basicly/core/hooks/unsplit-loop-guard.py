from __future__ import annotations

import json
import re
import sys

BLOCK_EXIT_CODE = 2

_SCALAR_ASSIGN = re.compile(
    r"""(?:^|[;&|\s])([A-Za-z_][A-Za-z0-9_]*)=(?P<q>["'])(?P<value>[^"']*)(?P=q)""",
    re.MULTILINE,
)

_UNSPLIT_LOOP = re.compile(
    r"""\bfor\s+[A-Za-z_][A-Za-z0-9_]*\s+in\s+\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?(?![\[\w])"""
)

_ADVICE = (
    "zsh does not word-split an unquoted scalar, so this loop runs ONCE with the whole "
    "string and exits 0 — it writes nothing and reports success.\n"
    "Use one of:\n"
    "  for x in a b c ...                 # an inline list\n"
    '  arr=(a b c); for x in "${arr[@]}"  # an array\n'
    "  <one batch command over all items>\n"
    "Then check the count actually changed — an unexpected count is a stop, not a footnote."
)


def command_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


def unsplit_loop_names(command: str) -> tuple[str, ...]:

    scalars = {
        match.group(1)
        for match in _SCALAR_ASSIGN.finditer(command)
        if match.group("value").strip() and len(match.group("value").split()) > 1
    }
    if not scalars:
        return ()
    looped = {match.group(1) for match in _UNSPLIT_LOOP.finditer(command)}
    return tuple(sorted(scalars & looped))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    names = unsplit_loop_names(command_text(payload))
    if not names:
        return 0
    subject = ", ".join(f"${name}" for name in names)
    print(f"unsplit-loop-guard: refusing a for-loop over {subject}.\n{_ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
