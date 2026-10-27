# .basicly/core/hooks

Git hook scripts — the deterministic, gating half of the harness. Fragments and
skills are the suggestive, non-deterministic guidance an agent reads; these scripts
are what actually blocks a bad commit/push regardless of whether the agent read or
followed the guidance. Both halves are first-class catalog citizens (see
[`docs/architecture/architecture.md`](../../../docs/architecture/architecture.md) §10, §13).

Scripts are invoked through the bundled [Lefthook](https://lefthook.dev/) runner.
`hooks.yaml` projects into shared `.basicly/lefthook.yml`, extended by the
consumer's `lefthook.yml`. Native Git and agent hooks call `lefthook-runtime.py`.
One dispatcher per event replays stdin to matched scripts and preserves agent
stdout, stderr and blocking exit codes through a private result channel.
Codex uses a separate Windows command and asks you to review new hook definitions
with `/hooks` before it runs them.

Git launchers verify that the managed dispatcher completed. If Lefthook skips
it because its native file selection is empty, the launcher runs only the
managed job once; foreign job filters still apply. Original Git arguments are
forwarded to consumer-owned Lefthook commands.

Git pre-commit runs against an isolated index snapshot. Successful mechanical
fixes update the index while preserving partially staged working files. Pre-push
never stashes ledger writes or ordinary unstaged edits.
Unchanged dotenv entries stay outside the snapshot; staged dotenv changes are
refused before materialization.
When the repository has a prepared `.venv`, snapshot checks reuse it with
`UV_NO_SYNC=1` to avoid rebuilding the project at every temporary path. When a
staged `uv.lock` exists, uv first checks lock freshness and installed dependencies
without installing the temporary project. Run
`uv sync --group dev` in the repository after changing its Python dependencies.

The table below is generated from [`hooks.yaml`](hooks.yaml) and each script's own
module docstring, and gated by `.scripts/docs_claims.py`.

<!-- docs-claims:begin catalog-hooks -->

| Hook | Stage | Manager | Script | Purpose |
| --- | --- | --- | --- | --- |
| `tracker-fold` | `post-merge` | `git` | [`tracker-fold.py`](tracker-fold.py) | Report pending tracker shards after a merge without changing the repository. |
| `tier-injection` | `pretooluse` | `claude` | [`../kit/tier/claude_tier_hook.py`](../kit/tier/claude_tier_hook.py) | Resolve a Claude spawn's declared model tier. |
| `protect-generated-codex` | `pretooluse` | `codex` | [`protect-generated.py`](protect-generated.py) | Block every generated-file path affected by a Codex patch. |
| `session-start-codex` | `sessionstart` | `codex` | [`session-start.py`](session-start.py) | Put the ledger's orientation in Codex's context at session open. |
| `markdownlint` | `pre-commit` | `git` | [`markdownlint.py`](markdownlint.py) | Run markdownlint-cli2 through a node this script resolves itself (basicly-jr0l.14). |
| `identity-guard` | `pre-commit` | `git` | [`identity-guard.py`](identity-guard.py) | Block commits made with an unconfigured or auto-derived git identity. |
| `pre-commit-script` | `pre-commit` | `git` | [`pre-commit.py`](pre-commit.py) | Run the configured fast checks before a commit. |
| `catalog-lint` | `pre-commit` | `git` | [`catalog-lint.py`](catalog-lint.py) | Pre-commit hook: validate catalog YAML sources via ``basicly catalog lint``. |
| `secret-scan` | `pre-commit` | `git` | [`secret-scan.py`](secret-scan.py) | Block a commit that stages a likely secret (basicly-yzyd). |
| `tracker-path-scan` | `pre-commit` | `git` | [`tracker-path-scan.py`](tracker-path-scan.py) | Block a commit that stages a machine-specific path in the tracker export (basicly-vkh0.5). |
| `internal-info-scan` | `pre-commit` | `git` | [`internal-info-scan.py`](internal-info-scan.py) | Block a commit that stages an internal-only identifier (basicly-0n3d). |
| `no-comments` | `pre-commit` | `git` | [`no-comments.py`](no-comments.py) | Enforce the selected comment policy; strict no-comments is the default. |
| `kit-boundary` | `pre-commit` | `git` | [`kit-boundary.py`](kit-boundary.py) | Fail when a kit module reaches back into basicly (basicly-vkh0.16). |
| `commit-msg-script` | `commit-msg` | `git` | [`commit-msg.py`](commit-msg.py) | Validate conventional commit message format. |
| `tracker-commit-msg-script` | `commit-msg` | `git` | [`tracker-commit-msg.py`](tracker-commit-msg.py) | Validate that a commit message references an issue id the tracker holds. |
| `tracker-claim-script` | `commit-msg` | `git` | [`tracker-claim.py`](tracker-claim.py) | Refuse a commit that changes files outside the ledger unless the committer holds a named record in progress. |
| `pre-push-script` | `pre-push` | `git` | [`pre-push.py`](pre-push.py) | Run the configured full checks before a push, and refuse one that would race a landing. |
| `protect-generated` | `pretooluse` | `claude` | [`protect-generated.py`](protect-generated.py) | Block agent edits to basicly-generated files (Claude Code PreToolUse hook). |
| `unsplit-loop-guard` | `pretooluse` | `claude` | [`unsplit-loop-guard.py`](unsplit-loop-guard.py) | Refuse a for-loop over an unsplit scalar (Claude Code PreToolUse hook, basicly-m2g3). |
| `pipe-status-guard` | `pretooluse` | `claude` | [`pipe-status-guard.py`](pipe-status-guard.py) | Refuse reading a pipeline's exit status when a filter ends it (PreToolUse, xkqxp9). |
| `bare-var-guard` | `pretooluse` | `claude` | [`bare-var-guard.py`](bare-var-guard.py) | Refuse a command whose head is a bare `$VAR` that same command assigned a phrase. |
| `rg-replace-guard` | `pretooluse` | `claude` | [`rg-replace-guard.py`](rg-replace-guard.py) | Refuse an `rg` short-flag cluster that swallows `-r`'s replacement value. |
| `headroom-guard` | `pretooluse` | `claude` | [`headroom-guard.py`](headroom-guard.py) | Put a Python module's remaining ratchet room in context before it is edited. |
| `protect-generated-commit` | `pre-commit` | `git` | [`protect-generated-commit.py`](protect-generated-commit.py) | Block a commit that stages a hand-edited basicly-generated file (git backstop). |
| `tool-usage` | `posttooluse` | `claude` | [`tool-usage.py`](tool-usage.py) | Count which terminal tools and skills the agent actually invokes (PostToolUse hook). |
| `tool-usage-copilot` | `posttooluse` | `copilot` | [`tool-usage.py`](tool-usage.py) | Count which terminal tools and skills the agent actually invokes (PostToolUse hook). |
| `session-start` | `sessionstart` | `claude` | [`session-start.py`](session-start.py) | Put the ledger's orientation in an agent's context at session open (basicly-yru8eu). |
| `session-start-copilot` | `sessionstart` | `copilot` | [`session-start.py`](session-start.py) | Put the ledger's orientation in an agent's context at session open (basicly-yru8eu). |

<!-- docs-claims:end catalog-hooks -->

`check_runner.py` is shared by the pre-commit and pre-push checks.
`lefthook-runtime.py` and `staged-snapshot.py` provide orchestration and index isolation.

## Installation

`basicly hooks-build` projects and activates the hooks. `basicly hooks-check`
checks the shared configuration, scripts, binary and native projections. Existing
Git hooks are chained and restored on uninstall. Consumer Lefthook jobs and
comments remain in the root configuration. Foreign pre-commit configurations
require migration to Lefthook before basicly removes the old managed wiring.

The immutable release archives, checksums, source archive and MIT license live
under `../vendor/lefthook/2.2.2`. The selected binary and license materialize in
`.basicly/bin` without a download. The Python runtime and uv are still required.
