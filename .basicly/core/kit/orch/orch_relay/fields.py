from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from orch_lessons.log import RefusedError

PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z0-9_ -]*>|\b(?:TODO|TBD|FIXME|XXX)\b")
RISK_SEPARATOR = "=>"


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


def risks(raw: list[str], action: str) -> list[Risk]:
    lines = {line.strip() for line in action.splitlines() if line.strip()}
    parsed: list[Risk] = []
    for entry in raw:
        risk, separator, check = entry.partition(RISK_SEPARATOR)
        risk, check = risk.strip(), check.strip()
        if not separator or not risk or not check:
            raise RefusedError(
                f"risk {entry!r} names no check; write it as --risk "
                f"'<risk> {RISK_SEPARATOR} <check line of the action>'"
            )
        if check not in lines:
            raise RefusedError(
                f"risk {risk!r} maps to no check line of the action; "
                f"add {check!r} as a line of --action, or drop the risk"
            )
        parsed.append(Risk(risk, check))
    return parsed
