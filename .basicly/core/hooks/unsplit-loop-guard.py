"""Refuse a for-loop over an unsplit scalar (Claude Code PreToolUse hook, basicly-m2g3).

Wired into ``.claude/settings.json`` by ``basicly hooks-build`` for the Bash tool.

zsh does not word-split an unquoted scalar, so ``V="a b c"; for x in $V`` runs the
body **once** with the whole string and exits 0. Nothing is written, nothing fails, and
the transcript is indistinguishable from a loop that did its work — which is the entire
reason this needs a gate rather than a rule. The rule already exists, always-on, in
``fragments/tools/non-interactive-shell``; it was in context and did not bind, and the
failure it describes was then committed anyway. A guard that fires at tool time is what
converts a silent no-op into a loud refusal.

**Why matching only same-command assignments is complete, not merely conservative.**
Shell state does not persist between Bash tool calls in this harness — each call is a
fresh shell — so a scalar can only reach a loop it breaks if both appear in the one
command. Widening beyond that buys no coverage and costs precision.

Deliberately not matched, each because it is correct or genuinely ambiguous:

- ``for x in "${arr[@]}"`` — the correct form this hook exists to steer toward.
- ``for x in a b c`` — an inline list.
- ``for x in $arr`` where ``arr`` is an array — zsh *does* split an array; only scalars
  are the trap, and an array assignment is ``name=(...)``.
- ``for x in $(cmd)`` — also unsplit under zsh, but idiomatic and usually intended.
  Blocking it would make the guard cry wolf, and a gate that cries wolf gets switched
  off, taking the true positives with it.
- a scalar whose value holds no whitespace — that loop correctly runs once.

The guard fails open by design: a malformed payload, a non-Bash call, or anything it
cannot parse exits 0, so a bug here can never lock an agent out of running commands. It
is a guardrail against a specific silent accident, not a security boundary.
"""

from __future__ import annotations

import json
import re
import sys

BLOCK_EXIT_CODE = 2

# A scalar assignment whose value is quoted and contains whitespace: `NAME="a b"` or
# `NAME='a b'`. An array is `name=(...)` and never matches, because `(` cannot open the
# quoted value. The value is captured to confirm the whitespace rather than assuming it.
_SCALAR_ASSIGN = re.compile(
    r"""(?:^|[;&|\s])([A-Za-z_][A-Za-z0-9_]*)=(?P<q>["'])(?P<value>[^"']*)(?P=q)""",
    re.MULTILINE,
)

# `for X in $NAME` / `${NAME}`, unquoted and without an index. `"$NAME"` is excluded on
# purpose: quoting it is an explicit choice to pass one word, not an accident.
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
    """The shell command a Bash tool call is about to run, or '' when there is none."""
    if not isinstance(payload, dict):
        return ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    command = tool_input.get("command")
    return command if isinstance(command, str) else ""


def unsplit_loop_names(command: str) -> tuple[str, ...]:
    """Names assigned a whitespace-bearing scalar and then looped over unsplit.

    The intersection is the whole check: either half alone is ordinary shell.
    """
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
    """Exit 2 to refuse the call when the loop would silently run once; 0 otherwise."""
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
