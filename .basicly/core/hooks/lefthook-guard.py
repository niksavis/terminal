from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

BLOCK_EXIT_CODE = 2

SEPARATORS = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")"})
PREFIXES = frozenset({"sudo", "exec", "command", "nohup", "npx", "env"})
NAMES = frozenset({"lefthook", "lefthook.exe"})
CONFIG = Path(".basicly") / "lefthook.yml"

ADVICE = (
    "in a basicly checkout a lefthook run without --no-auto-install, and every lefthook "
    "install, rewrites the git hooks that every worktree shares, so the next commit-msg "
    "gets no message file. Use one of:\n"
    "  python3 .basicly/core/hooks/HOOK.py FILE   # one check, as the hook runs it\n"
    "  git commit                                # every hook, through basicly's launcher\n"
    "  uv run basicly hooks-build                # reinstall basicly's hooks"
)


def command_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in {"bash", "shell"}:
        return ""
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    command = args.get("command") if isinstance(args, dict) else None
    return command if isinstance(command, str) else ""


def basicly_checkout(cwd: str) -> bool:
    start = Path(cwd)
    return any((folder / CONFIG).is_file() for folder in (start, *start.parents))


def words(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    return list(lexer)


def _in_command_position(tokens: list[str], index: int) -> bool:
    before = index - 1
    while before >= 0 and (tokens[before] in PREFIXES or "=" in tokens[before]):
        before -= 1
    return before < 0 or tokens[before] in SEPARATORS


def rewriting(command: str) -> tuple[str, ...]:
    try:
        tokens = words(command)
    except ValueError:
        return ()
    found: list[str] = []
    index = 0
    while index < len(tokens):
        name = tokens[index].rsplit("/", maxsplit=1)[-1]
        if name not in NAMES or not _in_command_position(tokens, index):
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and tokens[end] not in SEPARATORS:
            end += 1
        arguments = tokens[index + 1 : end]
        verbs = [token for token in arguments if not token.startswith("-")]
        verb = verbs[0] if verbs else ""
        if verb == "install" or (verb == "run" and "--no-auto-install" not in arguments):
            found.append(f"lefthook {verb}")
        index = end
    return tuple(found)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    command = command_text(payload)
    if not command:
        return 0
    cwd = str(payload.get("cwd") or ".") if isinstance(payload, dict) else "."
    if not basicly_checkout(cwd):
        return 0
    found = rewriting(command)
    if not found:
        return 0
    subject = ", ".join(f"`{item}`" for item in found)
    print(f"lefthook-guard: refusing {subject}: {ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
