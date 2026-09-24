---
name: model-tier
description: Declare and resolve a portable model tier for a subagent, so a spawn runs on the model the tier means for that host rather than the session default. Use when authoring or editing a subagent definition, when a subagent runs on the wrong model, or when deciding which model a task deserves.
---

# Model tiers

**A subagent declares a tier, not a model id.** The tiers are `low`, `medium`, `high` and
`maximum`. The kit resolves the tier into the model for the host and vendor in use. Thus one
definition works for different agent families, and a model rename is one edit to the map.

## Why a tier and not a model id

A model id in each definition is a duplicated fact. It becomes wrong without a warning: the
vendor retires the id, the spawn uses a different model, and nothing tells you. A tier tells
how much judgment the work needs. That stays true when the vendor changes its models.

Choose the tier by the work, not by caution:

| Tier | The work |
| --- | --- |
| `low` | mechanical, checkable, high volume: a sweep, a format, a count |
| `medium` | usual implementation with a clear specification |
| `high` | design judgment, an unclear requirement, a review that must find small faults |
| `maximum` | the few decisions that cost much when wrong and are difficult to undo |

If all work gets `high`, you use too much budget. If all work gets `low`, you must do the
work again. The tier is the decision.

## Resolve a tier

```sh
python3 .basicly/kit/tier/tier_resolver.py --host claude --tier low
python3 .basicly/kit/tier/tier_resolver.py --host copilot --tier high
python3 .basicly/kit/tier/tier_resolver.py --host claude --name <subagent> --default-tier medium
```

The resolver prints one JSON object. It exits 0 when it resolved a model and 1 when it did
not. **It fails closed:** an unavailable cell has no model, and the resolver never uses the
model of a different tier. Thus it never gives a wrong answer without a sign.

One model can have a different name on each surface. Thus `--host` changes the answer.

## Make a spawn use the tier

```sh
python3 .basicly/kit/tier/install_hook.py --dry-run   # print what it would write
python3 .basicly/kit/tier/install_hook.py             # this repository
```

On Claude Code, this installs a `PreToolUse` hook that adds the resolved model to a spawn.
**Quit and start the CLI again** if this was the first hook in a directory that the host did
not have before. To clear the conversation does not reload hooks. Without a restart, the hook
seems to do nothing, but each check says that it is installed.

On Copilot, the installer declines and tells why: that host selects the model of a subagent
in configuration, not through a hook. There, write the resolved model into the agent
definition yourself.

## Two traps

- **When `CLAUDE_CODE_SUBAGENT_MODEL` is set, the hook does nothing.** Examine that variable
  first when an injection seems to have no effect.
- **The hook writes the short alias, not the full model id.** The resolver prints both
  `alias` and `model`. Use the one that the surface uses.
