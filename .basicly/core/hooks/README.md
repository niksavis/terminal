# .basicly/core/hooks

Git hook scripts — the deterministic, gating half of the harness. Fragments and
skills are the suggestive, non-deterministic guidance an agent reads; these scripts
are what actually blocks a bad commit/push regardless of whether the agent read or
followed the guidance. Both halves are first-class catalog citizens (see
[`docs/architecture/architecture.md`](../../../docs/architecture/architecture.md) §10, §13).

Scripts are invoked by [pre-commit](https://pre-commit.com/) via
[`.pre-commit-config.yaml`](../../../.pre-commit-config.yaml). They are kept as
standalone Python files (no pre-commit-specific API) so they stay reusable by
lefthook or another hook manager, and so their logic is directly unit-testable.

The table below is generated from [`hooks.yaml`](hooks.yaml) and each script's own
module docstring, and gated by `.scripts/docs_claims.py`.

<!-- docs-claims:begin catalog-hooks -->

| Hook | Stage | Manager | Script | Purpose |
| --- | --- | --- | --- | --- |
| `identity-guard` | `pre-commit` | `git` | [`identity-guard.py`](identity-guard.py) | Block commits made with an unconfigured or auto-derived git identity. |
| `pre-commit-script` | `pre-commit` | `git` | [`pre-commit.py`](pre-commit.py) | Run the configured fast checks before a commit. |
| `catalog-lint` | `pre-commit` | `git` | [`catalog-lint.py`](catalog-lint.py) | Pre-commit hook: validate catalog YAML sources via ``basicly catalog lint``. |
| `secret-scan` | `pre-commit` | `git` | [`secret-scan.py`](secret-scan.py) | Block a commit that stages a likely secret (basicly-yzyd). |
| `tracker-path-scan` | `pre-commit` | `git` | [`tracker-path-scan.py`](tracker-path-scan.py) | Block a commit that stages a machine-specific path in the tracker export (basicly-vkh0.5). |
| `internal-info-scan` | `pre-commit` | `git` | [`internal-info-scan.py`](internal-info-scan.py) | Block a commit that stages an internal-only identifier (basicly-0n3d). |
| `kit-boundary` | `pre-commit` | `git` | [`kit-boundary.py`](kit-boundary.py) | Fail when a kit module reaches back into basicly (basicly-vkh0.16). |
| `commit-msg-script` | `commit-msg` | `git` | [`commit-msg.py`](commit-msg.py) | Validate conventional commit message format. |
| `tracker-commit-msg-script` | `commit-msg` | `git` | [`tracker-commit-msg.py`](tracker-commit-msg.py) | Validate that a commit message references an issue id the tracker holds. |
| `pre-push-script` | `pre-push` | `git` | [`pre-push.py`](pre-push.py) | Run the configured full checks before a push, and refuse one that would race a landing. |
| `protect-generated` | `pretooluse` | `claude` | [`protect-generated.py`](protect-generated.py) | Block agent edits to basicly-generated files (Claude Code PreToolUse hook). |
| `unsplit-loop-guard` | `pretooluse` | `claude` | [`unsplit-loop-guard.py`](unsplit-loop-guard.py) | Refuse a for-loop over an unsplit scalar (Claude Code PreToolUse hook, basicly-m2g3). |
| `pipe-status-guard` | `pretooluse` | `claude` | [`pipe-status-guard.py`](pipe-status-guard.py) | Refuse reading a pipeline's exit status when a filter ends it (PreToolUse, xkqxp9). |
| `headroom-guard` | `pretooluse` | `claude` | [`headroom-guard.py`](headroom-guard.py) | Put a Python module's remaining ratchet room in context before it is edited. |
| `protect-generated-commit` | `pre-commit` | `git` | [`protect-generated-commit.py`](protect-generated-commit.py) | Block a commit that stages a hand-edited basicly-generated file (git backstop). |
| `tool-usage` | `posttooluse` | `claude` | [`tool-usage.py`](tool-usage.py) | Count which terminal tools and skills the agent actually invokes (PostToolUse hook). |
| `tool-usage-copilot` | `posttooluse` | `copilot` | [`tool-usage.py`](tool-usage.py) | Count which terminal tools and skills the agent actually invokes (PostToolUse hook). |
| `session-start` | `sessionstart` | `claude` | [`session-start.py`](session-start.py) | Put the ledger's orientation in an agent's context at session open (basicly-yru8eu). |
| `session-start-copilot` | `sessionstart` | `copilot` | [`session-start.py`](session-start.py) | Put the ledger's orientation in an agent's context at session open (basicly-yru8eu). |

<!-- docs-claims:end catalog-hooks -->

Two Python files here are not hooks and so are absent from the table:
[`check_runner.py`](check_runner.py) is the config-driven runner the `pre-commit` and
`pre-push` scripts share, and [`markdownlint.py`](markdownlint.py) is wired directly
by [`.pre-commit-config.yaml`](../../../.pre-commit-config.yaml) as an unmanaged
(foreign) hook rather than through `hooks.yaml`.

## Status

This directory is the catalog source of truth this repo dogfoods directly
(`.pre-commit-config.yaml` points straight here). A fresh consumer repo installs
these hooks with `basicly hooks-build`, which materializes the scripts and merges
a managed `repo: local` block into `.pre-commit-config.yaml` (foreign repos/hooks
are preserved); `basicly hooks-check` reports drift. The hooks are described
tool-agnostically in [`hooks.yaml`](hooks.yaml) so another manager (e.g. lefthook)
can be projected later. See `docs/architecture/architecture.md` §10.2, §16.
