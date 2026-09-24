from __future__ import annotations

import os
import re
from collections.abc import Mapping

AGENT = "agent:"
OPERATOR = "operator"
AGENT_MARKERS = ("BR_AGENT_NAME", "AI_AGENT")
CLAUDE_CODE_MARKER = "CLAUDECODE"
CLAUDE_CODE = "claude-code"
MAX_NAME_CHARS = 64

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _name(raw: str) -> str:
    return _UNSAFE.sub("-", raw.strip()).strip("-")[:MAX_NAME_CHARS]


def writer_class(environ: Mapping[str, str] | None = None) -> str:

    values = os.environ if environ is None else environ
    for marker in AGENT_MARKERS:
        name = _name(values.get(marker, ""))
        if name:
            return AGENT + name
    if values.get(CLAUDE_CODE_MARKER) == "1":
        return AGENT + CLAUDE_CODE
    return OPERATOR
