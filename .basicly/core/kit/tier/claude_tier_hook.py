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
WORKER_TIERS = ("low", "medium", "high")

LOGGER = logging.getLogger("claude_tier_hook")


def takes_default_tier(tool_input: dict) -> bool:
    if tool_input.get(INPUT_MODEL_KEY):
        return False
    name = tool_input.get(SUBAGENT_KEY)
    return name is None or (isinstance(name, str) and name.strip() == DEFAULT_TIER_AGENT_TYPE)


def default_tier_setting() -> tuple[str | None, str | None]:
    raw = os.environ.get(tier_resolver.DEFAULT_TIER_ENV, "").strip()
    if not raw:
        return None, None
    if raw.lower() in WORKER_TIERS:
        return raw.lower(), None
    allowed = ", ".join(WORKER_TIERS)
    return None, (
        f"{tier_resolver.DEFAULT_TIER_ENV}={raw!r} is not a worker tier, so the tier hook "
        f"left this agent on the session model. Set it to one of {allowed} in the env "
        "block of a Claude settings file, or remove it."
    )


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
    resolver = tier_resolver.TierResolver.from_map_path(map_path, default_tier=fallback)
    if resolver is None:
        return None, False
    name = tool_input.get(SUBAGENT_KEY)
    definition = None
    if isinstance(name, str) and name.strip():
        definition = tier_resolver.find_definition(
            name.strip(), HOST, roots=tier_resolver.default_roots(cwd)
        )
    if definition is None:
        return (resolver.resolve(HOST).alias if fallback else None), wants_default
    if tier_resolver.declared_value(definition, tier_resolver.MODEL_KEY):
        return None, False
    declares_tier = bool(tier_resolver.declared_value(definition, tier_resolver.TIER_KEY))
    alias = resolver.resolve(HOST, definition=definition).alias
    return alias, wants_default and not declares_tier


def rewrite(payload: dict) -> dict | None:
    if payload.get("tool_name") != AGENT_TOOL:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if isinstance(raw_cwd, str) and raw_cwd else Path.cwd()
    default_tier, warning = (
        default_tier_setting() if takes_default_tier(tool_input) else (None, None)
    )
    alias, default_wanted = resolve_alias(tool_input, cwd, default_tier)
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
