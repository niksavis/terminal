# basicly v0.25.0 consumer validation

Record: `term-qe8sm3`. Date: 2026-10-15. Host: Linux under WSL, Git 2.55.0.

The upgrade used a sibling worktree and ordinary release-wheel installs, without
forcing conflicts or changing machine-wide permissions:

```sh
uvx --from https://github.com/niksavis/basicly/releases/download/v0.24.0/basicly-0.24.0-py3-none-any.whl basicly install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.24.1/basicly-0.24.1-py3-none-any.whl basicly install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.25.0/basicly-0.25.0-py3-none-any.whl basicly install
```

| Destination | Exit | Wall time | Wheel SHA256 |
| --- | --- | --- | --- |
| v0.24.0 | 0 | 6.737s | `8f6f4f55429a2097ee105daaff18fd4219af1173f702418a87535b44dae735b0` |
| v0.24.1 | 0 | 6.352s | `3f4de59aa5aab24c581e9818749d25ede01a53dd2282b8737b58476e489aeaad` |
| v0.25.0 | 0 | 6.492s | `e9403c3dc69f1942700f575a873b4d3c7a00916fa0a8ea51925211cbb384d42a` |

Digests matched GitHub's release asset metadata. All three cached wheel ZIP
integrity checks passed. These install timings include uv's wheel download and
environment preparation; they are single observations, not performance claims.

## Installed artifacts and ownership

`.basicly/bin/lefthook version` returned `2.2.2`. The Linux x86_64 executable and
`LICENSE.lefthook` matched the decompressed executable and MIT license in the
v0.25.0 wheel byte-for-byte. Executable SHA256:
`4fbf89eb7748c6aed84d833ee1a29edac48fae614468ca9a82896ec32f2800b6`.
The executable is a local generated artifact; CI restores it with
`basicly hooks-build --runtime-only` before checking hook drift.

The original base checkout had no staged work, an unstaged tracker shard and
untracked consumer-owned `.codex/config.toml`. The shard was preserved and folded
through the engine before the source commit. The user approved a permanent
repository-local `/.codex/config.toml` exclude. The consumer config stays
untracked; `.codex/hooks.json` is the managed hook projection.

`basicly.toml` and the user overlay were unchanged by installation. The base's
`core.hooksPath` was unset and remains unset. A separate installed consumer
retained its explicit `.consumer-hooks` path and its `basicly.toml` bytes.

The original Codex config lacks the new managed permission keys. In a disposable
consumer, `permissions-check` refused it, `permissions-build` added the missing
settings, and `permissions-check` then passed. A recursive comparison confirmed
every original consumer key/value survived. The user approved the same additive
repository-local merge after landing; no user-level permissions command is used.

## Git and agent behavior

A real `git commit` in the upgrade worktree was attempted with an undefined name
staged in `terminal_setup/configs.py` and the valid file restored only in the
working tree. Lefthook ran the existing checks and refused the commit:

```text
F821 Undefined name `basicly_missing_staged_name`
checks failed: 2/4 passed
```

The corrected probe verified that index bytes, staged entries, staged tree,
working-file bytes and HEAD were unchanged. The refusal took 3.199s. The original
index was restored from the probe's own backup afterward. The first probe had an
invalid assertion because it recorded index bytes before `git write-tree`
populated Git's cache metadata; the corrected probe captures them afterward.

In the disposable consumer, `git hook run --to-stdin=<input-file> pre-push`
executed the original foreign hook and all five configured full checks:

```text
foreign-pre-push
662 passed in 1.63s
checks passed: 5/5 in 3.87s
```

The hook received the input bytes exactly; wall time was 3.984s. A foreign hook
returning 37 made the installed launcher return exactly 37. The first stdin probe
used `git hook run` without `--to-stdin`; that invocation does not forward the
caller's stdin and was corrected before claiming preservation.

Seven agent cases compared direct scripts with the installed Lefthook launcher,
requiring identical stdout, stderr and exit status:

| Case | Exit | Launcher wall time |
| --- | --- | --- |
| Claude edit of a consumer file | 0 | 0.087s |
| Claude edit of a generated file | 2 | 0.075s |
| Codex patch: allowed file followed by generated file | 2 | 0.074s |
| Codex patch of a consumer file | 0 | 0.072s |
| Claude session start, text response | 0 | 0.324s |
| Codex session start, JSON response | 0 | 0.331s |
| Copilot session start, JSON response | 0 | 0.319s |

All seven comparisons passed. Blocking cases had empty stdout. Session-start
responses contained the tracker orientation without Lefthook console banners.

The retired `.pre-commit-config.yaml` contained these 14 hook IDs. Each remains
in the generated Git dispatcher, with `tracker-fold` added:

- `markdownlint`
- `identity-guard`
- `pre-commit-script`
- `catalog-lint`
- `secret-scan`
- `tracker-path-scan`
- `internal-info-scan`
- `no-comments`
- `kit-boundary`
- `commit-msg-script`
- `tracker-commit-msg-script`
- `tracker-claim-script`
- `pre-push-script`
- `protect-generated-commit`

## Repository checks

The initial full verification found one integration failure: the consumer's
`BASICLY_REF` still named v0.23.1. The existing pin-consistency regression test
failed while 661 tests passed. Updating the pin to v0.25.0 resolved it.

```text
662 passed in 1.64s
[verify] PASS (mode: full)
pre-commit passed: 6/6 checks in 2.14s
```

Full verification took 4.356s and ran the five checks declared in `basicly.toml`:
Ruff, Ruff formatting, Pyright, Bandit and pytest. The extended repository script
took 2.163s and also checked Markdown and the rendered cheat sheet.
Bandit reported no issues and retained an existing unused `nosec B604` warning.

The complete suite also passed with WSL detection forced to `False` in the five
terminal modules through a temporary autouse fixture: `662 passed in 1.67s`.
The fixture was removed after the run.

`check`, `skills-check`, `hooks-check`, `permissions-check`, `styles-check` and
`agents-check` passed in the upgraded worktree. `catalog lint` passed with
`56/60 = 93.3%` rank-1 routing against the configured 85% floor. Skills checking
reported an identical personal `cli-tools` skill shadowing the project copy.

## Limits

Two landings through the base's v0.23.1 engine passed all 662 tests but Git merge
exited 2. A disposable clone with the same hooks and local runtime merged
successfully. A targeted write probe then established that the active sandbox
mounts the base checkout's `.codex/` read-only (`Errno 30`), preventing Git from
creating the managed `.codex/hooks.json`. Landing requires task-scoped execution
approval, without changing machine-wide permission configuration.

The base also initially lacked the local Lefthook executable. The v0.25.0 wheel's
public `basicly hooks-build --runtime-only` installed it. That preparation alone
did not resolve the merge refusal. A v0.25.0 loop command against the old base
refuses the tracker-kit version mismatch, so the old engine performs the initial
landing.

The old engine hid Git's diagnostics and reported that its aborted merge left
the base clean, although
nine newly added source files remained untracked. Each was compared byte-for-byte
with the committed lane and preserved in a backup before retrying. No consumer
files were moved. Both findings were sent to the basicly migration session;
the upgrade does not modify upstream engine code.

Windows-native and macOS execution, actual coding-agent host callbacks and remote
CI are not established by these local probes. The agent checks exercise their
installed launchers with real stdin, not a newly started host process. Optional
affected selection and caching were not enabled. The existing consumer dev
dependency on pre-commit was retained; active Git orchestration uses Lefthook.

The upgrade commit, landing, final base checks and closing state are recorded on
`term-qe8sm3` after they occur. No hook bypass is authorized by this report.
