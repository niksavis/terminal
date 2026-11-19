from __future__ import annotations

import json
import logging
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

DEFAULT_TIER_AGENT_TYPE = "general-purpose"
MAXIMUM_ALIAS = tier_resolver.HOST_MODEL_ALIASES[HOST]["maximum"]
MAXIMUM_NOTICE = (
    "The maximum tier is for advice or orchestration. "
    "Use low, medium or high for a worker. The requested model remains unchanged."
)

LOGGER = logging.getLogger("claude_tier_hook")


class TierResolutionError(ValueError):
    pass


def takes_default_tier(tool_input: dict) -> bool:
    if tool_input.get(INPUT_MODEL_KEY):
        return False
    name = tool_input.get(SUBAGENT_KEY)
    return name is None or (isinstance(name, str) and name.strip() == DEFAULT_TIER_AGENT_TYPE)


def default_tier_setting() -> tuple[str | None, str | None]:
    raw = os.environ.get(tier_resolver.DEFAULT_TIER_ENV, "").strip()
    warning = tier_resolver.worker_default_error(raw)
    return (None, warning) if warning else (raw.lower() or None, None)


def resolve_alias(
    tool_input: dict, cwd: Path, default_tier: str | None = None
) -> tuple[str | None, bool]:

    if tool_input.get(INPUT_MODEL_KEY):
        return None, False
    map_path = tier_resolver.find_map(cwd, beside_the_kit=False)
    if map_path is None:
        return None, False
    wants_default = takes_default_tier(tool_input)
    fallback = default_tier if wants_default else None
    name = tool_input.get(SUBAGENT_KEY)
    definition = None
    if isinstance(name, str) and name.strip():
        definition = tier_resolver.find_definition(
            name.strip(), HOST, roots=tier_resolver.default_roots(cwd)
        )
    if definition is not None and tier_resolver.declared_value(definition, tier_resolver.MODEL_KEY):
        return None, False
    declared = tier_resolver.declared_tier(definition) if definition is not None else None
    failure = TierResolutionError(
        f"Agent {name!r} declares tier {declared!r}, but its model cannot resolve. "
        "Repair the model map or explicitly select a supported model."
    )
    try:
        resolver = tier_resolver.TierResolver.from_map_path(map_path, default_tier=fallback)
        alias = (
            resolver.resolve(HOST, definition=definition).alias if resolver is not None else None
        )
    except Exception:
        if not declared:
            raise
        LOGGER.exception("model resolution failed for an explicit agent tier")
        raise failure from None
    if declared and alias is None:
        raise failure
    return alias, wants_default and not declared


def rewrite(payload: dict) -> dict | None:
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") != AGENT_TOOL or not isinstance(tool_input, dict):
        return None
    if tool_input.get(INPUT_MODEL_KEY) == MAXIMUM_ALIAS:
        return {"systemMessage": MAXIMUM_NOTICE}
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    default_tier, warning = (
        default_tier_setting() if takes_default_tier(tool_input) else (None, None)
    )
    try:
        alias, default_wanted = resolve_alias(tool_input, cwd, default_tier)
    except TierResolutionError as error:
        return {
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT,
                "permissionDecision": "deny",
                "permissionDecisionReason": str(error),
            }
        }
    if alias is None:
        if warning is not None and default_wanted:
            return {"systemMessage": warning}
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
    except Exception:
        LOGGER.exception("the tier hook left this agent start unchanged after an internal error")
        return 0
    if output is not None:
        print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
