"""Refuse reading a pipeline's exit status when a filter ends it (PreToolUse, xkqxp9).

Wired into ``.claude/settings.json`` by ``basicly hooks-build`` for the Bash tool.

``cmd | tail`` exits with **tail's** status, so a failing gate reports success. The repo
already carries this as prose and it kept happening: twice on 2026-08-20, and before
that as a background run that notified "exit code 0" over a failed gate. It recurs
because the trap sits on the most travelled path there is — ``head`` and ``tail`` are
this repo's 1st and 3rd most-used tools (``_ADVICE`` carries the counts) — while the rule
against it is one sentence competing with an always-on budget that has 8 characters
spare. Guidance that must bind becomes a hook, which is what ``unsplit-loop-guard``
concluded about a rule that was in context and did not bind.

**The discriminator is that the status is read, not that a pipe exists.** Firing on
``cmd | tail`` itself would fire tens of thousands of times on the idiom, and a gate
that cries wolf gets switched off, taking its true positives with it. Shell state does
not persist between Bash tool calls here, so the use of the status is visible in the one
string or it is not this hook's business:

- ``$?`` read after the pipeline,
- ``&&`` or ``||`` chained after it, which branches on that status,
- the pipeline standing as an ``if``/``while``/``until`` condition,
- ``run_in_background``, where the only status the caller ever sees *is* the pipeline's,
  which is the shape of the recorded "exit code 0" incident.

Deliberately not matched, each because it is correct or genuinely ambiguous:

- ``set -o pipefail`` anywhere in the command — the pipeline's status is then the
  leftmost failure, which is the right answer and the fix this would otherwise demand.
- ``PIPESTATUS`` anywhere in the command — the caller is already handling it.
- a **grep-family** last stage. ``cmd | grep -q PASS && ...`` reads grep's status *on
  purpose*: matching is the assertion. So the fire set is a closed list of pass-throughs
  whose own status says nothing about what ran upstream.
- a single-stage command, and a pipeline whose status nothing in the string touches.

**The residual gap, stated rather than hidden.** This harness reports every Bash call's
exit code whether or not the command mentions it, so an agent can still misread a bare
``cmd | tail`` from the transcript with nothing syntactic to key on. That case is not
detectable here and is left to the advice below, which names the redirect form. The
guard closes the cases where the intent to branch on the status is written down.

The guard fails open by design: a malformed payload, a non-Bash call, or anything it
cannot parse exits 0, so a bug here can never lock an agent out of running commands.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# The sibling parser, imported the way `tool-usage.py` imports it: a hook is run by
# path under whatever interpreter the host provides, and a test loads it through
# `spec_from_file_location`, so neither puts this directory on `sys.path`.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import strip_heredocs

BLOCK_EXIT_CODE = 2

# Filters whose own exit status carries no information about the command upstream of
# them. `grep`/`rg` are absent on purpose: matching is an assertion and reading their
# status is usually the point (see the module docstring).
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

# `set -o pipefail` makes the pipeline's status the leftmost failure, and PIPESTATUS
# exposes each stage's. Either means the caller has already solved this.
_HANDLED = re.compile(r"\bPIPESTATUS\b|\bpipefail\b")

# A pipeline standing as a condition: the status is the branch, whatever follows.
_CONDITION_HEAD = re.compile(r"^\s*(?:if|while|until)\b")

_OPERATORS = ("||", "&&")


def command_text(payload: object) -> str:
    """The shell command a Bash tool call is about to run, or '' when there is none."""
    return _tool_input(payload).get("command") or "" if _tool_input(payload) else ""


def runs_in_background(payload: object) -> bool:
    """True when the call is backgrounded, so the reported code is the pipeline's."""
    return _tool_input(payload).get("run_in_background") is True


def _tool_input(payload: object) -> dict:
    """The tool_input mapping of a Bash call, or {} for anything else."""
    if not isinstance(payload, dict):
        return {}
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if str(tool).lower() not in {"bash", "shell"}:
        return {}
    args = payload.get("tool_input") or payload.get("toolArgs") or {}
    return args if isinstance(args, dict) else {}


def split_with_operators(command: str) -> list[tuple[str, str]]:
    """Segments paired with the operator that ended each, quote- and escape-aware.

    ``shell_tokens.split_pipeline_segments`` flattens ``| || && ;`` into one list, which
    loses the distinction this needs: ``a | tail`` and ``a | tail && b`` differ only by
    the operator after the last stage. Quote handling matches that function's, for its
    reason — an operator inside ``-m "fix; ship"`` is text.
    """
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
    """The command name a segment starts with, lowercased, or '' when it has none."""
    for token in segment.strip().split():
        if token and "=" not in token:
            return token.rsplit("/", maxsplit=1)[-1].lower()
    return ""


def unread_pipe_filters(command: str, *, background: bool = False) -> tuple[str, ...]:
    """The pass-through filters whose pipeline status this command actually reads.

    Empty when nothing here is the defect, which is the answer for the overwhelming
    majority of the 30354 recorded ``head``/``tail`` invocations.
    """
    text = strip_heredocs(command)
    if _HANDLED.search(text):
        return ()
    parts = split_with_operators(text)
    found: list[str] = []
    for index, (segment, operator) in enumerate(parts):
        if index == 0 or parts[index - 1][1] != "|":
            continue  # not the tail of a pipeline
        name = _head_token(segment)
        if name not in PASS_THROUGH:
            continue
        if background or operator in _OPERATORS or _reads_status(parts, index):
            found.append(name)
    return tuple(dict.fromkeys(found))


def _next_command(parts: list[tuple[str, str]], index: int) -> str | None:
    """The first segment after *index* that runs something; a blank or ``#`` line does not."""
    for segment, _ in parts[index + 1 :]:
        stripped = segment.strip()
        if stripped and not stripped.startswith("#"):
            return segment
    return None


def _reads_status(parts: list[tuple[str, str]], index: int) -> bool:
    """True when ``$?`` reads *this* pipeline's status, or the pipeline is a condition.

    ``$?`` holds the status of the command immediately before it, so a command in between
    claims it; scanning the whole invocation refused the block `_ADVICE` recommends
    (basicly-g8jxj3).
    """
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
    """Exit 2 to refuse the call when a filter's status would be read as the gate's."""
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
