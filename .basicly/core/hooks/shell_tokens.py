from __future__ import annotations

import re
import shlex
from pathlib import Path

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
    "break",
    "continue",
    "declare",
    "function",
    "in",
    "local",
    "readonly",
    "return",
    "shift",
    "{",
    "}",
    "(",
    ")",
}

WRAPPER_TOKENS = {
    "uv",
    "uvx",
    "npx",
    "env",
    "sudo",
    "xargs",
    "command",
    "exec",
    "nohup",
    "time",
}

WRAPPER_SUBCOMMANDS = {"run", "tool"}

WRAPPER_VALUE_FLAGS = {
    "--directory",
    "--project",
    "--python",
    "--with",
    "--from",
    "--package",
    "-C",
    "-u",
}

WRAPPER_STOP_TOKENS = {"python", "-m"}

_HEREDOC = re.compile(r"<<-?\s*\\?(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1")

_FUNCTION_DEF = re.compile(
    r"(?:^|[\n;&|])\s*"
    r"(?:function\s+(?P<keyword>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))"
)

_COMMAND_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def split_pipeline_segments(command: str) -> list[str]:

    segments: list[str] = []
    buf: list[str] = []
    quote: str | None = None
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if ch == "\\" and quote != "'" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if quote != "'" and (command[i : i + 2] == "$(" or ch == "`"):
            segments.append("".join(buf))
            buf = []
            i += 2 if ch == "$" else 1
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


def strip_heredocs(command: str) -> str:
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


def _shell_functions(command: str) -> set[str]:
    return {match["keyword"] or match["name"] for match in _FUNCTION_DEF.finditer(command)}


def skip_wrapper_args(tokens: list[str]) -> list[str]:

    while tokens:
        head = tokens[0]
        if head in WRAPPER_STOP_TOKENS:
            return []
        if head in WRAPPER_VALUE_FLAGS:
            tokens = tokens[2:]
            continue
        if head in WRAPPER_SUBCOMMANDS or head.startswith("-") or "=" in head:
            tokens = tokens[1:]
            continue
        break
    return tokens


def segment_tokens(segment: str) -> list[str]:

    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def tools_in_command(command: str) -> list[str]:
    tools: list[str] = []
    text = strip_heredocs(command)
    functions = _shell_functions(text)
    for segment in split_pipeline_segments(text):
        tokens = segment_tokens(segment)
        while tokens:
            head = tokens[0]
            if "=" in head and not head.startswith("-"):
                tokens.pop(0)
                continue
            if head in SKIP_TOKENS or head in functions or head.startswith("-"):
                tokens = []
            break
        while tokens:
            name = Path(tokens[0]).name
            if not name or not _COMMAND_NAME.match(name):
                break
            tools.append(name)
            if name in WRAPPER_TOKENS:
                tokens = skip_wrapper_args(tokens[1:])
                continue
            break
    return tools
