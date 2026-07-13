# .basicly/core/hooks

Git hook scripts — the deterministic, gating half of the harness. Fragments and
skills are the suggestive, non-deterministic guidance an agent reads; these scripts
are what actually blocks a bad commit/push regardless of whether the agent read or
followed the guidance. Both halves are first-class catalog citizens (see
[`docs/architecture.md`](../../../docs/architecture.md) §3, §4).

Scripts are invoked by [pre-commit](https://pre-commit.com/) via
[`.pre-commit-config.yaml`](../../../.pre-commit-config.yaml). They are kept as
standalone Python files (no pre-commit-specific API) so they stay reusable by
lefthook or another hook manager, and so their logic is directly unit-testable.

| Hook         | Script                                       | Purpose                                |
| ------------ | -------------------------------------------- | -------------------------------------- |
| `pre-commit` | [`pre-commit.py`](pre-commit.py)             | ruff, pyright, bandit, markdownlint    |
| `commit-msg` | [`commit-msg.py`](commit-msg.py)             | Conventional commit format check       |
| `commit-msg` | [`beads-commit-msg.py`](beads-commit-msg.py) | Requires a known beads (`br`) issue id |
| `pre-push`   | [`pre-push.py`](pre-push.py)                 | pytest                                 |

## Status

This directory is the catalog source of truth this repo dogfoods directly
(`.pre-commit-config.yaml` points straight here). There is no `hooks-build` /
`hooks-check` projection command yet for installing these hooks into a fresh
consumer repo — see `docs/architecture.md` §11 for that gap.
