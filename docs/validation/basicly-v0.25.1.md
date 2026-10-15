# basicly v0.25.1 consumer validation

Record: `term-bzfgkl`. Date: 2026-10-15. Host: Linux under WSL.

The v0.25.0 checkout started clean at `00c435d`. Consumer configuration and Git
configuration were backed up before the upgrade. A separate tracked sibling
worktree received the ordinary release-wheel install:

```sh
uvx --from https://github.com/niksavis/basicly/releases/download/v0.25.1/basicly-0.25.1-py3-none-any.whl basicly install
```

The wheel passed ZIP integrity checking and matched both the release handover and
GitHub's published SHA256:
`e268ea18fa5babedff85836c5b0762bcf0422b4bbf548695fdc8a97bbf79ac47`.
Installation exited 0 in 1.071s with the wheel already cached. This is one timing
observation, not a speed comparison against the earlier download-inclusive run.

## Protected-write refusal

The exact public install command above was also run in the native Codex sandbox
from the base checkout, after confirming the destination was protected. It
refused before applying the upgrade:

```text
Cannot write planned destination <checkout>/.agents/skills/harness-loop/SKILL.md: Read-only file system.
Stopped before changing the repository.
For an already-authorized operation, retry `basicly install` in this checkout through task-scoped execution review.
```

Exit was 1 in 0.327s. Before/after comparisons matched HEAD, porcelain-v2 status,
the index bytes and SHA256 of every existing tracked regular file returned by
`git ls-files -z`, excluding dotenv names. They also matched the original
`.codex/config.toml`, `.git/config` and `.git/info/exclude`. No tracked file,
catalog state or consumer configuration changed. A separate direct probe of the
released preflight function refused the base's protected `.codex/hooks.json`.
These probes used actual native sandbox mounts, without simulated permissions.

The linked-worktree install succeeded in its native sandbox. The base landing
uses task-scoped reviewed execution for the protected `.agents/` projection,
retaining normal hooks, signing and dotenv denials. No machine-wide permission
configuration is changed. The new engine's install preflight is demonstrated;
landing starts with the engine matching the base's existing tracker kit.

## Ownership and hooks

All existing shared Git launchers and saved foreign-hook files retained their
SHA256, modification time and mode across installation. The base's consumer
Codex config, `basicly.toml`, local Git config and local exclude file remained
byte-identical. The config stays untracked; `core.hooksPath` remains unset.

A disposable consumer with an explicit `.consumer-hooks` path and a foreign
pre-push hook also installed v0.25.1. Repeating installation took 0.574s and
preserved every launcher and foreign backup in bytes, modification time and mode.
Its consumer `basicly.toml` and configured hook path survived. Native execution
with `git hook run --to-stdin=<input-file> pre-push` received stdin exactly and
ran the foreign hook plus the existing full checks:

```text
foreign-pre-push
662 passed in 2.12s
checks passed: 5/5 in 4.29s
```

The hook's wall time was 4.430s. A foreign refusal returned exactly 37 through
the installed launcher.

The repository-local executable reports Lefthook 2.2.2. Its bytes and the MIT
license match the v0.25.1 wheel's bundled artifacts.

Seven agent cases compared the installed launcher with direct scripts, requiring
exact stdout, stderr and exit status. Allowed Claude and Codex edits returned 0;
generated-file edits returned 2 with empty stdout. The Codex refusal included a
patch whose allowed file preceded a protected file. Claude's session-start text
and Codex/Copilot session-start JSON matched exactly, without Lefthook banners.

## Repository checks

The existing pin-consistency regression test covers the terminal skill pin,
which was aligned to v0.25.1 together with contributor commands and installer
repins. The five full checks declared by `basicly.toml` passed:

```text
662 passed in 2.25s
[verify] PASS (mode: full)
pre-commit passed: 6/6 checks in 2.20s
```

Full verification took 5.096s. The extended repository checks took 2.227s and
included Markdown and the rendered cheat sheet. Bandit retained its existing
unused `nosec B604` warning and found no issues. A second full test run with WSL
detection forced off in the five terminal modules passed all 662 tests in 1.69s;
the temporary autouse fixture was removed afterward.

`check`, `skills-check`, `hooks-check`, `permissions-check`, `styles-check`,
`agents-check` and `catalog lint` passed. Routing remained `56/60 = 93.3%` against
the configured 85% floor. The identical personal `cli-tools` skill still shadows
the project copy.

A real partial-stage commit was refused in 3.066s on an undefined name present
only in the index. The working file had the valid content. Index bytes, staged
tree, working-file bytes and HEAD remained unchanged; the probe's own index copy
was restored afterward. The successful ordinary commit, merged-base verdict,
closure and final push are recorded on `term-bzfgkl` after they occur. The earlier
[v0.25.0 report](basicly-v0.25.0.md) retains the preceding migration evidence.

## Limits

These local probes do not establish Windows-native or macOS execution, actual
coding-agent host callbacks, or remote CI success. Optional affected selection
and caching remain disabled. No upstream workflow fix is implemented in terminal.
