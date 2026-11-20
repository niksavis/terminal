from __future__ import annotations

import json
import shlex
import sys

BLOCK_EXIT_CODE = 2

KILLERS = frozenset({"pkill", "pgrep"})
SEPARATORS = frozenset({";", "&&", "||", "|", "&", "\n", "(", ")"})
PREFIXES = frozenset({"sudo", "exec", "xargs", "command", "nohup"})

ADVICE = (
    "the pattern is also in the command line of the shell that runs this command, so "
    "it matches that shell and kills it (Exit code 144). Use one of:\n"
    "  pkill -f '[m]argin'      # a bracket class does not match its own text\n"
    "  kill <pid>               # take the PID from pgrep -a '[m]argin' or a pid file"
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


def words(command: str) -> list[str]:
    lexer = shlex.shlex(command.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    return list(lexer)


def _matches_full_line(options: list[str]) -> bool:
    for option in options:
        if option == "--full":
            return True
        if option.startswith("-") and not option.startswith("--") and "f" in option[1:]:
            return True
    return False


def _in_command_position(tokens: list[str], index: int) -> bool:
    before = index - 1
    while before >= 0 and tokens[before] in PREFIXES:
        before -= 1
    return before < 0 or tokens[before] in SEPARATORS


def self_matching(command: str) -> tuple[str, ...]:
    try:
        tokens = words(command)
    except ValueError:
        return ()
    found: list[str] = []
    index = 0
    while index < len(tokens):
        name = tokens[index].rsplit("/", maxsplit=1)[-1]
        if name not in KILLERS or not _in_command_position(tokens, index):
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and tokens[end] not in SEPARATORS:
            end += 1
        arguments = tokens[index + 1 : end]
        options = [token for token in arguments if token.startswith("-")]
        patterns = [token for token in arguments if not token.startswith("-")]
        if _matches_full_line(options) and patterns and "[" not in patterns[-1]:
            found.append(f"{name} -f {patterns[-1]}")
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
    found = self_matching(command)
    if not found:
        return 0
    subject = ", ".join(f"`{item}`" for item in found)
    print(f"pkill-self-match: refusing {subject}: {ADVICE}", file=sys.stderr)
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
