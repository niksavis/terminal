from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import strip_heredocs

BLOCK_EXIT_CODE = 2

PASS_THROUGH = frozenset({
    "head",
    "tail",
    "cat",
    "tee",
    "nl",
    "wc",
    "sort",
    "uniq",
    "column",
    "less",
    "more",
    "fold",
    "rev",
})

_HANDLED = re.compile(r"\bPIPESTATUS\b|\bpipefail\b")

_CONDITION_HEAD = re.compile(r"^\s*(?:if|while|until)\b")

_OPERATORS = ("||", "&&")


def command_text(payload: object) -> str:
    return _tool_input(payload).get("command") or "" if _tool_input(payload) else ""


def runs_in_background(payload: object) -> bool:
    return _tool_input(payload).get("run_in_background") is True


def _tool_input(payload: object) -> dict:
    if not isinstance(payload, dict):
        return {}
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in {"bash", "shell"}:
        return {}
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    return args if isinstance(args, dict) else {}


def split_with_operators(command: str) -> list[tuple[str, str]]:

    out: list[tuple[str, str]] = []
    buf: list[str] = []
    quote: str | None = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < n:
            buf.append(ch + command[i + 1])
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
        if command[i : i + 2] in _OPERATORS:
            out.append(("".join(buf), command[i : i + 2]))
            buf = []
            i += 2
            continue
        if ch in (";", "|", "\n", "&"):
            out.append(("".join(buf), ch))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append(("".join(buf), ""))
    return out


def _head_token(segment: str) -> str:
    for token in segment.strip().split():
        if token and "=" not in token:
            return token.rsplit("/", maxsplit=1)[-1].lower()
    return ""


def unread_pipe_filters(command: str, *, background: bool = False) -> tuple[str, ...]:

    text = strip_heredocs(command)
    if _HANDLED.search(text):
        return ()
    parts = split_with_operators(text)
    found: list[str] = []
    for index, (segment, operator) in enumerate(parts):
        if index == 0 or parts[index - 1][1] != "|":
            continue
        name = _head_token(segment)
        if name not in PASS_THROUGH:
            continue
        if background or operator in _OPERATORS or _reads_status(parts, index):
            found.append(name)
    return tuple(dict.fromkeys(found))


def _next_command(parts: list[tuple[str, str]], index: int) -> str | None:
    for segment, _ in parts[index + 1 :]:
        stripped = segment.strip()
        if stripped and not stripped.startswith("#"):
            return segment
    return None


def _reads_status(parts: list[tuple[str, str]], index: int) -> bool:

    following = _next_command(parts, index)
    if following is not None and "$?" in following:
        return True
    start = index
    while start > 0 and parts[start - 1][1] == "|":
        start -= 1
    return bool(_CONDITION_HEAD.match(parts[start][0]))


_ADVICE = (
    "the pipeline's exit status is the FILTER's, not the command's, so a failing gate "
    "reports success — head is this repo's most-used tool at 16394 calls and tail is "
    "third at 13960, which is why this is a hook and not a note.\n"
    "Use one of:\n"
    "  <cmd> > out.txt 2>&1; echo $?; tail -5 out.txt   # no pipe to mis-read\n"
    "  <cmd> | tail -5; echo ${PIPESTATUS[1]}           # the stage you meant\n"
    "  set -o pipefail; <cmd> | tail -5                 # leftmost failure wins\n"
    "Then confirm the result from the explicit pass/fail summary line, not from the "
    "exit code alone — truncated output hides failures."
)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    command = command_text(payload)
    if not command:
        return 0
    names = unread_pipe_filters(command, background=runs_in_background(payload))
    if not names:
        return 0
    subject = ", ".join(f"`{name}`" for name in names)
    print(f"pipe-status-guard: refusing a status read after {subject}: {_ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
