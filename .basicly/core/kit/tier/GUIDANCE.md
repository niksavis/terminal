---
name: model-tier
description: Declare and resolve a portable model tier for a subagent, so a spawn runs on the model the tier means for that host rather than the session default. Use when authoring or editing a subagent definition, when a subagent runs on the wrong model, or when deciding which model a task deserves.
---

# Model tiers

**A subagent declares a tier, not a model id.** `low`, `medium`, `high`, `maximum`. The kit
resolves that tier into the concrete model for the host and vendor in play, so one
definition works across agent families and a model rename is one edit to a map rather than
one per definition.

## Why a tier and not a model id

A model id pinned into a definition is a fact duplicated in every definition, and it goes
stale silently: the id is retired, the spawn falls back, and nothing says so. A tier is a
statement about the *work* — how much judgment it needs — which stays true when the vendor's
line-up changes.

Choose by the work, not by caution:

| Tier | The work |
| --- | --- |
| `low` | mechanical, checkable, high volume — a sweep, a format, a count |
| `medium` | ordinary implementation with a clear specification |
| `high` | design judgment, an ambiguous requirement, a review that must catch subtle faults |
| `maximum` | the few decisions that are expensive to get wrong and hard to reverse |

Defaulting everything to `high` wastes budget; defaulting everything to `low` produces work
that has to be redone. The tier is the decision.

## Resolve one

```sh
python3 .basicly/kit/tier/tier_resolver.py --host claude --tier low
python3 .basicly/kit/tier/tier_resolver.py --host copilot --tier high
python3 .basicly/kit/tier/tier_resolver.py --host claude --name <subagent> --default-tier medium
```

It prints one JSON object and exits 0 when it resolved, 1 when it did not. **It fails
closed**: an unavailable cell carries no model and it never substitutes a neighbouring
tier's, so a wrong answer is never returned quietly.

The same model can be spelled differently per surface, which is why `--host` matters and
not only for cosmetics.

## Make a spawn actually use it

```sh
python3 .basicly/kit/tier/install_hook.py --dry-run   # print what it would write
python3 .basicly/kit/tier/install_hook.py             # this repository
```

On Claude Code this installs a `PreToolUse` hook that rewrites a spawn to the resolved
model. **Quit and relaunch the CLI afterwards** if this was the first hook written into a
directory the host did not already have — clearing the conversation does not reload hooks,
and the hook then appears to do nothing while every diagnostic says it is installed.

On hosts with no hook that can rewrite a spawn, the installer **declines and says why**
rather than reporting a success for a hook that would never fire. There the fallback is to
put the resolved model in the definition's own frontmatter and pass it on the session
command line.

## Two traps that cost real time

- **An environment variable that pins the subagent model outranks the hook.** Where it is
  set every injection is inert and the hook stays silent. Check it first when an injection
  appears not to work.
- **The spawn parameter takes a short alias, the definition frontmatter takes a full id.**
  They are different vocabularies on the same host. The resolver prints both; use the one
  the surface wants.
