from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from orch_lessons.log import RefusedError

PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_ -]*>|\b(?:TODO|TBD|FIXME|XXX)\b")
RISK_SEPARATOR = "=>"
RISK_EXAMPLE_CHECK = "gh run watch --exit-status"
RISK_EXAMPLE = (
    f"--action 'git push origin main\n{RISK_EXAMPLE_CHECK}' "
    f"--risk 'red CI {RISK_SEPARATOR} {RISK_EXAMPLE_CHECK}'"
)
EXAMPLE_HEADS = {
    "orch decide": (
        "orch decide --item push --repo app "
        "--rule 'The orchestrator decides ask-first items.' --rule-date 2026-11-18 "
        "--reason 'the lane passed its checks' --condition 'CI is green on the pushed commit' "
        f"--proof '{RISK_EXAMPLE_CHECK}' --if-proof-fails 'revert the push and report it'"
    ),
    "orch approve": "orch approve --item deploy --repo app --words 'go'",
}


@dataclass(frozen=True)
class Risk:
    risk: str
    check: str


def require(fields: Mapping[str, str | None], command: str) -> None:
    missing = [name for name, value in fields.items() if not (value or "").strip()]
    if missing:
        names = ", ".join(f"--{name}" for name in missing)
        raise RefusedError(f"{command} refuses an incomplete message; give {names}")


def no_placeholder(fields: Mapping[str, str | None], command: str) -> None:
    for name, value in fields.items():
        hit = PLACEHOLDER.search(value or "")
        if hit:
            raise RefusedError(
                f"{command} refuses --{name}: it holds the placeholder {hit.group(0)!r}; "
                "send only a complete, checked text"
            )


def example(command: str) -> str:
    head = EXAMPLE_HEADS.get(command)
    return f"{head} {RISK_EXAMPLE}" if head else RISK_EXAMPLE


def risks(raw: list[str], action: str, command: str = "orch decide") -> list[Risk]:
    lines = {line.strip() for line in action.splitlines() if line.strip()}
    parsed: list[Risk] = []
    problems: list[str] = []
    for entry in raw:
        risk, separator, check = entry.partition(RISK_SEPARATOR)
        risk, check = risk.strip(), check.strip()
        if not separator or not risk or not check:
            problems.append(f"risk {entry!r} names no check")
        elif check not in lines:
            problems.append(
                f"risk {risk!r} maps to no check line of the action; "
                f"add {check!r} as a line of --action"
            )
        else:
            parsed.append(Risk(risk, check))
    if problems:
        raise RefusedError(
            f"{command} refuses --risk: {'; '.join(problems)}. Write each risk as "
            f"'RISK {RISK_SEPARATOR} CHECK', where CHECK is also one line of --action, "
            f"or drop the risk. Example that passes: {example(command)}"
        )
    return parsed
