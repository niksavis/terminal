"""Pin a Claude Code subagent spawn to its declared tier (PreToolUse hook).

The first consumer of ``tier_resolver.py`` beside it, and the injection half of
basicly-wbsz: a subagent definition declares a portable ``tier``, and this hook
turns that into the concrete model the spawn actually runs on, at spawn time,
with **no basicly** — same constraint as the resolver, because the two files
travel together into a repository that has never heard of this harness.

Wire it into ``settings.json`` as a ``PreToolUse`` hook matching the ``Agent``
tool. On stdout it emits, and nothing else::

    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "updatedInput": {...the whole original input...}}}

``updatedInput`` **replaces** the tool input rather than merging into it, which
is why every original key is copied through and only ``model`` is added.

**It writes an alias, not a model id.** Measured against the 2.1.220 binary on
basicly-wbsz.2: the Agent tool's ``model`` parameter is
``enum(["sonnet","opus","haiku","fable"])``, so the resolver's full id
(``claude-opus-5``) is rejected there — a different vocabulary from the same
host's definition *frontmatter*, which documents a full id as legal.
``tier_resolver.HOST_MODEL_ALIASES`` holds the mapping and a test holds it to the
map.

Six ways it declines to rewrite, all of them silent on stdout so the host's own
resolution stands untouched:

- the call is not an ``Agent`` spawn;
- ``CLAUDE_CODE_SUBAGENT_MODEL`` is set — it **outranks** the per-invocation
  parameter this hook writes, so a rewrite would be inert, and pretending
  otherwise would hide which model the spawn really used;
- the tool input already carries a ``model``, or the definition's frontmatter
  declares one — either way the question is already answered;
- the spawn's own directory tree has no model map;
- nothing resolves: no tier declared, an unknown tier, or a cell the map marks
  unavailable. **Never a neighbouring tier's model.**

The map is looked up from the spawn's working directory with the resolver's
kit-adjacent fallback **off** (``beside_the_kit=False``). That is not a detail:
the kit is by definition always beside itself, so with the fallback on, a hook
installed once per machine — which is how the copilot half must be installed,
and how a user-level ``settings.json`` installs this one — would inject a model
into every unrelated repository on the machine. Measured on basicly-wbsz.2.

Malformed input, an unreadable file, or any unexpected error exits 0 with no
output. This is a convenience in the spawn path, not a security boundary, and a
bug in it must never be able to stop an agent from spawning.

Written to the same older-interpreter bar as the resolver: no syntax newer than
3.9, one exception class per handler (this repo's ``ruff format`` targets 3.14
and would rewrite a parenthesized multi-exception ``except`` into syntax the
consumer's python may not have).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Imported after the path insert above, and by bare name: the kit is a directory
# of two sibling files, not a package, so a relative import is not available.
import tier_resolver

HOST = "claude"
AGENT_TOOL = "Agent"
HOOK_EVENT = "PreToolUse"

# Keys of the Agent tool's *input*: the subagent name arrives in the first and
# the resolved alias is written into the second. Spelled the same as the
# definition frontmatter's ``tier_resolver.MODEL_KEY`` and deliberately kept
# separate from it — two surfaces of the same host, and only one of them is
# limited to the four-value enum.
SUBAGENT_KEY = "subagent_type"
INPUT_MODEL_KEY = "model"

# Set on the machine, this outranks the per-invocation parameter the hook writes
# (documented resolution order: this, then the parameter, then the definition
# frontmatter, then the main conversation model).
OVERRIDE_ENV = "CLAUDE_CODE_SUBAGENT_MODEL"


def resolve_alias(tool_input: dict, cwd: Path) -> str | None:
    """The alias to pin this spawn to, or ``None`` to leave the spawn alone.

    Every ``None`` here is a deliberate decline, not a failure: the caller emits
    nothing and the host resolves the model the way it would have anyway.
    """
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
    """The hook's stdout payload for one PreToolUse event, or ``None`` for none."""
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
    # A copy, with one key added: `updatedInput` replaces the arguments, so
    # dropping anything here would drop it from the spawn.
    updated = dict(tool_input)
    updated[INPUT_MODEL_KEY] = alias
    return {"hookSpecificOutput": {"hookEventName": HOOK_EVENT, "updatedInput": updated}}


def main() -> int:
    """Read the PreToolUse payload from stdin; print a rewrite or nothing."""
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
