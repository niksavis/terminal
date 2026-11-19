from __future__ import annotations

import json
import re
from pathlib import Path

from orch_lessons.log import RefusedError

VENDORS = ("claude", "copilot", "codex")
ROLE_FILES = Path(".agents/roles")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def launch(vendor: str, role: str, name: str, repo: Path) -> list[str]:
    if CONTROL.search(name) or not name.strip():
        raise RefusedError(
            "orch start refuses --name: give a non-empty name with no control characters"
        )
    if vendor == "claude":
        return ["claude", "--agent", role, "-n", name]
    if vendor == "copilot":
        return ["copilot", "--agent", role]
    if vendor == "codex":
        role_file = repo / ROLE_FILES / f"{role}.md"
        if not role_file.is_file():
            raise RefusedError(
                f"{ROLE_FILES / (role + '.md')} is missing in {repo}; turn on the "
                "orchestration feature of basicly and run basicly install"
            )
        text = role_file.read_text(encoding="utf-8")
        return ["codex", "-c", f"developer_instructions={json.dumps(text)}"]
    raise RefusedError(f"orch start refuses vendor {vendor!r}; use one of: {', '.join(VENDORS)}")
