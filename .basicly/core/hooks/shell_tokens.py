"""Take one shell command apart into the command names it actually invokes.

One responsibility, and it is the shell text: split a command into its pipeline
segments, drop the parts that are data rather than commands (here-document bodies,
functions the text defines), and walk past the wrappers that stand between the head
token and the tool the operator meant (``uv run --directory <path> pytest`` is
pytest, not the path). Everything here is a pure function of a string.

Split out of ``tool-usage.py`` when the module-size ratchet caught that hook growing.
The boundary is *parsing* against *recording*: nothing here reads or writes a file,
knows what a Claude or Copilot payload looks like, or decides what is worth counting
— ``tool-usage.py`` does all three and asks this module what a command ran. Nothing
here imports back, which is what lets the parsing be tested as text.

A sibling module rather than a hook, deployed exactly as ``check_runner.py`` is: the
catalog copies every file in this directory into a consumer's tree, and the importer
puts this directory on ``sys.path`` itself so the import survives a host that runs the
hook by path and a test that loads it through ``spec_from_file_location``. **stdlib
only**, by the hooks convention — no interpreter running a hook is guaranteed to have
this repo's package importable.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

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
    # Control-flow and declaration words that head their own line inside a
    # multi-line loop or function body, where the newline split makes them a
    # segment head of their own (basicly-m0p1).
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

# Wrappers whose *argument* is the interesting tool (`uv run pytest` counts
# both uv and pytest). `env` is one of them: `env -C <dir> <cmd>` and
# `env FOO=1 <cmd>` were crediting env alone and losing the tool.
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

# A wrapper's own subcommand names no tool: keep walking to the real command.
WRAPPER_SUBCOMMANDS = {"run", "tool"}

# Wrapper flags whose value is a *separate* argv item, so both must be skipped:
# `uv run --directory <worktree> pytest` credited the worktree's basename as the
# tool 49 times and never credited pytest (basicly-m0p1). The `--flag=value`
# form needs no entry here — it is a single token the generic flag skip drops.
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

# Inline code, not a tool invocation: nothing after these is a command name.
WRAPPER_STOP_TOKENS = {"python", "-m"}

# `cmd <<TAG` / `cmd <<-'TAG'` / `cmd <<\TAG`: everything until the terminator
# line is data, not commands — counting heredoc body lines as tools was
# basicly-587. The optional backslash disables expansion (`<<\EOF`); missing it
# left those bodies unstripped and leaked their keywords/terminator (basicly-v7eu).
_HEREDOC = re.compile(r"<<-?\s*\\?(['\"]?)(?P<tag>[A-Za-z_][A-Za-z0-9_]*)\1")

# `name() {` / `function name {`: a function defined in the command text is not a
# tool, so neither is the call to it later in that same text (`write_src`, counted
# 3 times as a terminal tool — basicly-m0p1).
_FUNCTION_DEF = re.compile(
    r"(?:^|[\n;&|])\s*"
    r"(?:function\s+(?P<keyword>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))"
)

# A command name, once the basename is taken: anything else is shell text that
# survived tokenisation rather than something that was run.
_COMMAND_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def split_pipeline_segments(command: str) -> list[str]:
    """Split on the pipeline operators ``|| && ; |`` and newlines outside quotes.

    Splitting the raw string with a regex would shatter a quoted argument that
    contains an operator or newline — a multi-line ``git commit -m`` body, a
    ``--title "add x; ship it"`` — into fake segments whose first word is then
    miscounted as a command head (basicly-zcvo). Tracking quote state keeps
    quoted-string contents inside a single segment.

    A command substitution opener (``$(``, a backtick) is also a boundary: it runs
    a real command, and gluing it to the token before it — ``id=$(tool create ...)``
    — made the *subcommand* the head, so ``create`` and ``run`` (64 counts) entered
    the table instead of the tool (basicly-m0p1).
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
        # Inside '...' a substitution is literal text, so quote state still decides.
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


def _shell_functions(command: str) -> set[str]:
    """Names of the shell functions *command* defines; calling one names no tool."""
    return {match["keyword"] or match["name"] for match in _FUNCTION_DEF.finditer(command)}


def skip_wrapper_args(tokens: list[str]) -> list[str]:
    """Advance past a wrapper's subcommands, flags, flag values and VAR=val prefixes.

    One interleaved walk rather than one ordered pass per kind: a flag can precede
    the subcommand (``uv --directory <path> run pytest``) and a flag's value can be
    a separate argv item (``uv run --directory <path> pytest``), and the old fixed
    order credited that value as the tool (basicly-m0p1).
    """
    while tokens:
        head = tokens[0]
        if head in WRAPPER_STOP_TOKENS:
            return []
        if head in WRAPPER_VALUE_FLAGS:
            tokens = tokens[2:]  # the flag *and* the value that follows it
            continue
        if head in WRAPPER_SUBCOMMANDS or head.startswith("-") or "=" in head:
            tokens = tokens[1:]
            continue
        break
    return tokens


def segment_tokens(segment: str) -> list[str]:
    """*segment* as argv, falling back to a whitespace split on unbalanced quotes.

    ``shlex.split`` mangles backslashes under POSIX rules, which would corrupt a
    Windows path in an argument. Harmless for every caller here, which keep only
    command and flag *names* and discard every value.
    """
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def tools_in_command(command: str) -> list[str]:
    """Head tokens (basenames) of every pipeline segment, wrappers unwrapped."""
    tools: list[str] = []
    text = strip_heredocs(command)
    functions = _shell_functions(text)
    for segment in split_pipeline_segments(text):
        tokens = segment_tokens(segment)
        while tokens:
            head = tokens[0]
            if "=" in head and not head.startswith("-"):
                tokens.pop(0)  # VAR=val prefix: skip it and keep scanning for the head
                continue
            if head in SKIP_TOKENS or head in functions or head.startswith("-"):
                tokens = []  # a builtin, a local function, or a stray flag names no tool
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
