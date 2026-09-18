from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tier_resolver

HOST = "claude"
AGENT_TOOL = "Agent"
HOOK_EVENT = "PreToolUse"

SUBAGENT_KEY = "subagent_type"
INPUT_MODEL_KEY = "model"

OVERRIDE_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"


def resolve_alias(tool_input: dict, cwd: Path) -> str | None:

    if tool_input.get(INPUT_MODEL_KEY):
        return None
    map_path = tier_resolver.find_map(cwd, beside_the_kit=False)
    if map_path is None:
        return None
    resolver = tier_resolver.TierResolver.from_map_path(map_path)
    if resolver is None:
        return None
    name = tool_input.get(SUBAGENT_KEY)
    definition = None
    if isinstance(name, str) and name.strip():
        definition = tier_resolver.find_definition(
            name.strip(), HOST, roots=tier_resolver.default_roots(cwd)
        )
    if definition is None:
        return None
    if tier_resolver.declared_value(definition, tier_resolver.MODEL_KEY):
        return None
    return resolver.resolve(HOST, definition=definition).alias


def rewrite(payload: dict) -> dict | None:
    if payload.get("tool_name") != AGENT_TOOL:
        return None
    if os.environ.get(OVERRIDE_ENV, "").strip():
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    alias = resolve_alias(tool_input, cwd)
    if alias is None:
        return None
    updated = dict(tool_input)
    updated[INPUT_MODEL_KEY] = alias
    return {"hookSpecificOutput": {"hookEventName": HOOK_EVENT, "updatedInput": updated}}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    except OSError:
        return 0
    if not isinstance(payload, dict):
        return 0
    try:
        output = rewrite(payload)
    except OSError:
        return 0
    if output is not None:
        print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
