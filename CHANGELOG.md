# Changelog

All notable user-facing changes are documented in this file by release tag.

## v0.9.0 - 2026-09-25

Delta: v0.8.1..v0.9.0

### Highlights

- **A fresh Ubuntu WSL now gets every tool in one run.** Nine tools used to be compiled with `cargo`, which fails on a fresh distro because it has no C compiler. Now fd, bat, ripgrep, xh, ast-grep, sd, just, delta, typos, fzf, jq, yq, shellcheck, git-lfs and direnv come from each project's latest release binary. Each binary is checked against the sha256 digest GitHub records for it. Installs take seconds instead of minutes, and rustup and cargo are no longer installed (term-hfntv).
- **Re-runs tell you what is out of date.** A tool at the latest release is skipped with "is up to date". An older one is left alone with "rerun with --update", and `--update` installs the latest. Checking for a new release no longer uses the GitHub API, so repeated runs do not hit its rate limit; if a download does, set `GITHUB_TOKEN` (term-hfntv).
- **New: one sudo step for the system packages a fresh WSL lacks.** When `zsh`, `tree`, `podman`, `bubblewrap` or `socat` are missing, setup asks once to run `sudo apt-get update && sudo apt-get upgrade -y && sudo apt-get install -y` for exactly those packages. If you decline, if the run cannot prompt, or with `--no-sudo`, it prints the command instead. `podman` lets you run container images; `bubblewrap` and `socat` are what the Claude Code sandbox (`/sandbox`) needs on WSL2. `podman-docker`, which adds a `docker` command backed by podman, is added only when no Docker is installed, because it would replace an existing `docker.io` (term-hfntv).
- **Fixed: on Windows, setup wrote a `tool-tree` skill for the built-in `tree.com`**, which is not GNU tree. Programs under the Windows system directory no longer count as installed tools (term-hfntv).
- **To pick it up**, run the full setup (not `--only config`): `uvx --from git+https://github.com/niksavis/terminal@v0.9.0 terminal-setup`. On a fresh WSL, answer yes to the apt prompt, or run the command it prints.

### Commit delta (auto-generated)

- fix(setup): check release download urls and satisfy pyright and bandit (term-hfntv) (c296b85)
- docs(release): update changelog for v0-9-0 (term-hfntv) (bf59c00)
- chore(release): bump package version for next release (term-hfntv) (fe71b70)
- feat(setup): prepare a fresh wsl without a compiler and in one apt step (term-hfntv) (83630b1)

## v0.8.1 - 2026-09-25

Delta: v0.8.0..v0.8.1

### Highlights

- **Fixed: setup output no longer prints shell scripts that look like warnings.** Each step that runs an inline script used to echo the whole script, so a run from Windows showed lines such as `Claude Code not detected ($HOME/.claude missing)` even when Claude Code was there and the step succeeded. Setup now prints one short line per step, for example `wsl -d Ubuntu-24.04 --exec sh: install the basicly cli-tools skills` or `pwsh -NoProfile: add the starship prompt to the PowerShell profile`. What the steps do, and any message or error they print, is unchanged (term-77zcv).
- **To pick it up**, nothing is needed beyond running setup from this version: `uvx --from git+https://github.com/niksavis/terminal@v0.8.1 terminal-setup`.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-77zcv) (083db4b)
- fix(setup): print a label for scripted steps instead of the script (term-77zcv) (a5b6be1)
- chore(tracker): record the first real v0-8-0 setup run (term-h88v7) (f7a6239)
- chore(tracker): close the v0-8-0 release record (term-h88v7) (bfb68c6)

## v0.8.0 - 2026-09-25

Delta: v0.7.0..v0.8.0

### Highlights

- **New: Claude Code gets a skill for each command-line tool setup installs.** Setup now writes the basicly `cli-tools` skill and one `tool-<name>` skill per tool it finds (`rg`, `fd`, `jq`, `bat`, `yq` and the rest) into `~/.claude/skills`. An agent in any repository then picks the fast installed tool instead of a slower default, and knows its flags. Run from Windows, setup writes them both in WSL and in `%USERPROFILE%\.claude`, each side with the tools present there; run inside WSL or on Linux or macOS, there. A tool that is not installed gets no skill, and a rerun removes the skill of a tool that is gone while leaving your other skills alone. It needs network access to fetch basicly v0.18.9 with `uv`, is skipped when `~/.claude` is missing, and `--skip-claude` skips it. A failure is reported as a failed step and does not stop the rest of the config deploy (term-h88v7).
- **To pick it up, run the setup again**; `--only config` is enough, because the skills are written during config deploy.
- **Maintainers: the basicly harness moves from 0.18.2 to 0.18.9.** Tracker claims record the holder from git identity, which works on any forge, and identity-guard refuses a commit that adds the git user name anywhere else; the old ledger prose was scrubbed accordingly (term-uqs3o, term-gatuy, term-z8sd4). basicly `skills-user` now refuses a skill name it does not know instead of skipping it. A test fails whenever the basicly version setup installs skills from drifts from the harness version, or when basicly adds a tool skill that setup does not map (term-h88v7).

### Commit delta (auto-generated)

- chore(harness): upgrade basicly to v0-18-9 and repin setup skills (term-h88v7) (633ea5e)
- docs(release): update changelog for v0-8-0 (term-h88v7) (da6f4f2)
- chore(release): bump package version for next release (term-h88v7) (1c32fc8)
- feat(setup): install the basicly cli-tools skills for the tools it finds (term-h88v7) (332c14b)
- docs(overlay): require setup features to cover windows and wsl via clone and uvx (term-n5hj3) (27084c6)
- chore(tracker): close the held fold record (term-z8sd4) (447a61b)
- chore(tracker): redact the git user name from old ledger prose (term-z8sd4) (3613557)
- chore(tracker): fold pending writer shards into the trunk log (term-ftosv) (6240efc)
- chore(harness): upgrade basicly to v0-18-8 (term-z8sd4) (3b32c35)
- chore(tracker): close the v0-18-7 upgrade record (term-gatuy) (e05a4cb)
- chore(harness): upgrade basicly to v0-18-7 (term-gatuy) (c8f00e5)
- chore(tracker): file the v0-18-7 upgrade for next session (term-99z) (846a432)
- chore(tracker): file the approved retro proposals for next session (term-99z) (518712f)
- chore(tracker): record the session handover (term-99z) (bd5173b)
- chore(tracker): close the v0-18-6 upgrade record (term-uqs3o) (a5a8252)
- chore(harness): upgrade basicly to v0-18-6 (term-uqs3o) (fec9781)
- chore(tracker): close the v0-7-0 release record (term-m1ubo) (25aed9a)

## v0.7.0 - 2026-09-24

Delta: v0.6.1..v0.7.0

### Highlights

- **New: `img-zoom`, an image zoom command for coding agents.** Agents read dense images - screenshots, charts, technical drawings - more accurately when they can crop part of the full-resolution original and look at it enlarged. `img-zoom IMAGE X1 Y1 X2 Y2 -o OUT.png` does that and prints the image size and the crop box, so the agent can check its coordinates; `img-zoom --info IMAGE` prints the size first. It works on image files only. Setup installs it with `uv tool install`: run from Windows, both in WSL and natively on Windows, with its folder added to your user PATH; run inside WSL or on Linux or macOS, there. `img-zoom --python` prints a Python that has Pillow and OpenCV, for an agent's own measuring scripts (Pillow only on Windows on ARM, where OpenCV has no build) (term-u1hdq, term-534cp).
- **Claude Code learns that `img-zoom` exists.** Setup writes a skill to `~/.claude/skills/img-zoom/SKILL.md` - in WSL, and in `%USERPROFILE%\.claude` when run from Windows - only where Claude Code is installed and `img-zoom` is present, so the skill never points at a missing command. `--skip-claude` skips it, as it skips the status line (term-u1hdq, term-534cp).
- **`uv tool upgrade` keeps working after `uv cache clean`.** Setup installs `img-zoom` from a copy it keeps in `~/.local/share/terminal-setup` (Windows: `%LOCALAPPDATA%\terminal-setup`), not from uv's cache, which a cache clean removes (term-9bmbl).
- **Fixed: the Claude Code status line was blank on a stock Mac.** macOS ships bash 3.2, and the script used bash 4 features, so it failed without a word. It now runs on bash 3.2 or newer; its output is unchanged everywhere else. The README now documents `STATUSLINE_NERDFONT` and `STATUSLINE_WIDTH` (term-zb5lg).
- **Maintainers: CI now runs the tests on Windows and macOS too**, not only on Ubuntu. The first run is what found the macOS status line bug (term-7yv4e). The basicly harness moves from 0.15.0 to 0.18.2, and ruff no longer requires docstrings, because basicly's no-comments gate forbids them (term-dq7l5, term-np3i3, term-rdfqj).
- **To pick it up, run the full setup** (not `--only config`): `img-zoom` is an install step, and the skill is written only where `img-zoom` is present. On Windows, restart the terminal afterwards so the new PATH entry applies.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-m1ubo) (3c2f8ad)
- chore(tracker): close the cross-platform ci and macos bash records (term-zb5lg) (d5c429a)
- fix(statusline): run on the old bash that ships with macos (term-zb5lg) (de19a88)
- ci: run the test suite on windows and macos (term-7yv4e) (569ed14)
- chore(tracker): close the stable-copy record (term-9bmbl) (b0bae95)
- fix(agents): install img-zoom from a stable copy (term-9bmbl) (1d6aeac)
- chore(tracker): record the full windows setup run (term-534cp) (d76d89a)
- chore(tracker): close the uvx and windows img-zoom record (term-534cp) (5e26fd4)
- fix(agents): ship img-zoom in the package and install it on windows (term-534cp) (ba322f7)
- chore(tracker): close img-zoom after a real setup run (term-u1hdq) (edfead9)
- chore(tracker): close the v0-18-2 upgrade record (term-np3i3) (d2797a4)
- chore(harness): upgrade basicly to v0-18-2 (term-np3i3) (f3faacc)
- chore(tracker): close the upgrade and gate conflict records (term-rdfqj) (f99107f)
- feat(agents): add img-zoom image crop-and-zoom command (term-u1hdq) (8de6768)
- chore(lint): follow no-comments over ruff pydocstyle (term-rdfqj) (923095a)
- chore(harness): upgrade basicly to v0-18-1 (term-dq7l5) (ade64ce)
- chore(harness): upgrade basicly to v0-15-0 (term-1050f) (9d77586)
- chore(tracker): record the v0-15-0 pre-upgrade findings (term-1050f) (2e40bcf)
- chore(tracker): file the unconditional install advice (term-ip2wz) (596c993)
- chore(tracker): propose the positive-control refinement (term-2vkce) (b8492cc)
- chore(tracker): close the markdownlint blocker (term-fawxo) (d4e0b15)
- chore(harness): upgrade basicly to v0-14-2 (term-fawxo) (539d37b)
- chore(tracker): file the unannounced ci scaffold writes (term-42xuc) (43a9b9e)
- chore(tracker): file the ledger merge-driver gaps (term-n3rzn) (6ccd6d4)
- chore(tracker): correct the wezterm staleness premise (term-31j) (700f997)
- chore(tracker): record the session handover (term-99z) (62f8290)

## v0.6.1 - 2026-09-12

Delta: v0.6.0..v0.6.1

### Highlights

- **A failing tool no longer ends the whole setup.** Installing a tool reaches the network and someone else's release assets, so it fails for reasons unrelated to everything queued behind it - an outage, a renamed asset, an API rate limit. Until now any one of those aborted the run, taking with it every step not yet reached, config deployment included, which needs no network at all. Each tool install is now isolated: the failure is reported with the tool's own error, the run carries on, and the end of the run names every failed step. The exit status is still non-zero, so a script is never told a partial setup succeeded (term-jet6e).
- **Refresh runs no longer rebuild Rust tools that are already current.** `cargo install --force` rebuilds from source whether or not anything changed, spending minutes of compilation to land an identical binary. The version is now checked against crates.io first - which is what cargo would install, and not always a project's newest git tag: `sd`'s latest release is tagged v1.1.0 while only 1.0.0 was ever published, so comparing against tags would rebuild for ever. An unreachable crate or a missing binary still installs (term-jet6e).

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-jet6e) (1f36882)
- fix(install): keep one failing tool from ending the whole setup (term-jet6e) (b2b756c)

## v0.6.0 - 2026-09-12

Delta: v0.5.1..v0.6.0

### Highlights

- **Node.js in WSL/Linux/macOS moves from v24 to v26.** This setup installs Node into WSL but leaves Windows-native Node alone, so the pinned major is what keeps the two sides on one line - and that had lapsed: a machine with Windows on v26.8.2 still got v24 in WSL. v26 is the Current line for another six weeks and becomes Active LTS on 2026-10-28, eight days after v24 drops to maintenance, so the old pin was behind rather than conservatively stable. Pick it up with `terminal-setup --update`, which refreshes Node and the other user-local tools to their latest releases; `--only config` does not touch runtimes (term-uhxvn).
- The README no longer claims the two sides match automatically. Windows-native Node is outside this setup's control, so it now says where to check (`node --version` on each) rather than asserting a match it cannot enforce.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-uhxvn) (64af247)
- feat(node): track the node line the windows runtime is on (term-uhxvn) (00b4a26)

## v0.5.1 - 2026-09-12

Delta: v0.5.0..v0.5.1

### Highlights

- **The Fable gauge now fades as its reading ages, instead of looking current when it is not.** That figure is a snapshot: it comes from the usage snapshot Claude Code caches, and only `/usage` and `/cost` write that cache - using Fable does not refresh it. A reading from 55 minutes ago therefore looked identical to one from a second ago. It now renders in full colour for ten minutes after a refresh, in the dim colour after that, and disappears once past the cache's own one-hour lifetime. Colour alone carries it, so no duration is added that could be misread as a countdown (term-sinhx).
- **Fixed: the package reported version 0.1.0.** `terminal_setup.__version__` had sat at 0.1.0 through every release since, because the release bumps `pyproject.toml` alone and nothing compared the two. Nothing reads the attribute today, so there is no behaviour change - but it was wrong, and anyone reading it would have believed it (term-4ph26).
- **Maintainers: a release can no longer publish a version nobody bumped.** A new pre-flight compares the tag against `pyproject.toml`, `terminal_setup/__init__.py`, `uv.lock` and the changelog heading, naming every disagreement in one run, and the release workflow runs the same check before publishing - so skipping the pre-flight is harmless rather than silent. Publishing is now also gated on the full `quality-gates` suite passing against the tagged tree: neither gate workflow triggered on tags before, so a published tag inherited its green from `main` having been pushed first. CI also passes `uv sync --locked`, because a bare `uv sync` rewrites a stale lockfile rather than failing on it, masking the drift (term-l0ym3, term-0bl0c).
- Re-apply with `terminal-setup --only config`. No restart is needed on any platform.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-sinhx) (f859e5b)
- fix(statusline): fade the per-model gauge as its sample ages (term-sinhx) (0ad58c9)
- ci(release): gate publishing on the gates and refuse a stale lockfile (term-0bl0c) (adea098)
- ci(release): refuse a tag that disagrees with the declared version (term-l0ym3) (ac1eb15)
- fix(version): bring the package version attribute into step with pyproject (term-4ph26) (d53e47b)

## v0.5.0 - 2026-09-12

Delta: v0.4.6..v0.5.0

### Highlights

- **The status line now shows both of Claude Code's weekly limits.** Claude bills some models against a weekly window of their own on top of the all-models one - `/usage` calls it "Current week (Fable)" - and the status line only ever rendered the all-models figure. The binding constraint could therefore sit at 83% while the visible gauge read 61%. Both now render side by side under one shared reset, since the two windows are the same week and reset within a microsecond of each other: `wk 61% - fable 83% 4d`. When a model has no window of its own the segment collapses to the all-models gauge alone, so nothing needs changing if that distinction ever goes away (term-4dnxa).
- **That per-model figure is sampled, not live.** Claude Code holds the window in its own rate-limit store but does not put it on the status line's stdin, so it is read from the usage snapshot Claude Code caches in its config file - which only `/usage` and `/cost` refresh. A sample past the one-hour lifetime Claude Code itself gives that cache is dropped rather than shown, so the gauge goes quiet instead of going wrong. Run `/usage` to refresh it (term-4dnxa).
- **The universal (`--no-nerd-font`) build now renders outside a Nerd Font terminal.** Four of its glyphs - the worktree, branch, reset and model markers - are in no Windows console font and appeared as tofu boxes in PowerShell and Git Bash, and the gauge blocks were absent from Consolas and Lucida Console, which blanked the bar outright. Every glyph is now chosen against the cmap of Consolas, Cascadia Mono, Lucida Console and DejaVu Sans Mono, and a test asserts it over the rendered output rather than trusting that a codepoint looks ordinary. The worktree marker turned out to be in none of those fonts, so it was tofu in WezTerm too (term-4dnxa).
- **The gauges resolve to half a cell rather than a whole one**, so 60% no longer looks like 70% and 83% no longer looks like 97%. They are also drawn as one solid block in two colours instead of a solid fill against a dithered trough, whose texture read as a break in the bar (term-4dnxa).
- Re-apply with `terminal-setup --only config`. No restart is needed on any platform: the status line script is executed afresh on every render, so a replaced file takes effect immediately.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-4dnxa) (486d944)
- feat(statusline): show the per-model weekly limit and repair the glyph set (term-4dnxa) (7a91f39)
- chore(tracker): file the session retro findings and handover (term-99z) (a6d6933)
- chore(tracker): correct the wezterm upgrade scope on term-31j (term-31j) (af1c758)
- chore(tracker): record the migration and close the release record (term-99z) (c9eb38c)
- chore(tracker): cut over from beads to the owned ledger (term-99z) (a6b3f6d)

## v0.4.6 - 2026-09-11

Delta: v0.4.5..v0.4.6

### Highlights

- **Windows: the launch menu now opens Windows shells on Windows.** PowerShell, Git Bash, and Command Prompt had no `domain` on their launcher entries, so WezTerm fell back to `CurrentPaneDomain` — and since the default tab on Windows is the WSL domain, picking one of them started it *inside WSL*. Git Bash died immediately (its Windows path is not in the WSL filesystem namespace); pwsh and cmd limped along through WSL interop with WSL cwd semantics. All three are now pinned to the `local` domain, as is the "open config in notepad" action (term-tqk).
- **Windows: a WSL-only startup command no longer leaks onto the local domain.** `config.default_prog` was set globally, so it applied to the local domain too and `wezterm cli spawn --domain-name local` (with no explicit program) tried to run `zsh -lc …` on the Windows side. The spawn returned a pane id and exit 0 while the shell died at once with "didn't exit cleanly" and the pane reported an empty cwd — a failure that looked like success. The startup args now live only on the WSL domain entry (term-o2u).
- Each launcher entry opens as its own tab, so WSL, PowerShell, and Git Bash can run side by side. The launcher is reachable by right-clicking the `+` button in the tab bar as well as with `Ctrl + Shift + l`; both are now documented in the README and the cheat sheet.
- Internal only, no effect on installed terminals: the packaged basicly harness moved from 0.5.1 to a clean v0.12.1 install. This retires the vendored-engine era — `.scripts/sync-basicly.py` and its tests are gone, CI and the VS Code tasks are pinned to a released tag instead of tracking a branch, and the agent guidance, skills, and git hooks were regenerated from the 0.12.1 catalog (term-99z).
- Re-apply with `terminal-setup --only config`. Restart WezTerm on Windows to pick up the launcher and domain changes; on Linux and macOS there is nothing to re-apply.

### Commit delta (auto-generated)

- chore(basicly): upgrade the harness to v0-12-1 and re-pin the gates (term-99z) (bec2643)
- chore(release): bump package version for next release (term-99z) (7840802)
- chore(basicly): retire the vendoring script and ignore br sidecar files (term-99z) (77ded78)
- chore(beads): record the upstream reply and close the release-page wait (term-99z) (9ce896a)
- chore(beads): record the post-install state of play for pickup (term-99z) (5ede3c4)
- chore(basicly): replace the harness with a clean v0-12-0 install (term-99z) (0e0a97a)
- chore(beads): record the v0-12-0 clean-install runbook from basicly (term-99z) (22c677c)
- chore(beads): record the decision to wait for the basicly release (term-99z) (5be1c92)
- chore(beads): correct the recorded ci failure cause (term-99z) (6f6c5af)
- chore(beads): switch to a clean-install plan and file the broken build task (term-99z) (51bf628)
- chore(beads): record the br-to-new-tracker migration checklist (term-99z) (28e2269)
- chore(beads): record the catalog-lint root cause and close the launcher bug (term-99z) (49d1b9a)
- fix(wezterm): pin windows launcher profiles to the local domain (term-tqk) (b6a5c53)
- chore(beads): track the basicly upgrade and release follow-up (term-99z) (f599f97)
- chore(beads): close the wezterm local domain tracker issue (term-o2u) (35b863a)
- fix(wezterm): scope wsl startup args to the wsl domain (term-o2u) (44767a0)

## v0.4.5 - 2026-07-23

Delta: v0.4.4..v0.4.5

### Highlights

- Internal only, no effect on installed terminals: the packaged basicly harness was restamped from 0.3.0 to 0.5.1 (regenerated `CLAUDE.md` / `AGENTS.md` / copilot-instructions, new secret-scan and protect-generated-commit hooks, refreshed permissions and skills), converging `basicly check` in CI. A follow-up to v0.4.4, which shipped the starship `scan_timeout` fix but landed just before this restamp.
- Also internal: a Windows-portability test fix (bash path narrowed to satisfy pyright), completing the v0.4.4 test work.
- Nothing to re-apply — no change to any deployed terminal config.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-irs) (b09322f)
- chore(beads): close the harness restamp tracker issue (term-irs) (e3864f7)
- fix(tests): narrow bash path to satisfy pyright (term-h65) (a4d0412)
- chore(basicly): restamp the install for the 0-5-1 harness upgrade (term-irs) (3ea38c0)
- chore(beads): close starship and test-portability issues (term-f0z) (d12ae68)

## v0.4.4 - 2026-07-23

Delta: v0.4.3..v0.4.4

### Highlights

- **No more "Scanning current directory timed out" warnings on shell startup.** Starship's `scan_timeout` was at the 30ms default, which is too low wherever directory scanning is slow — WSL drvfs (`/mnt/c`), large repos, or a cold filesystem cache — so Starship aborted the module-detection scan and printed the warning (seen in WSL and Git Bash). The timeout is now 500ms, letting the scan finish; the fast path is unaffected since the ceiling only bites when a scan is genuinely slow. Mirrors the earlier `command_timeout` fix.
- Internal, no effect on installed terminals: the statusline and runner tests are now portable on Windows (they had assumed Linux tool paths, the WSL `bash` stub, and a non-UTF-8 encoding), and the packaged basicly install was re-stamped for a harness upgrade.
- Re-apply with `terminal-setup --only config`; no WezTerm restart is needed.

### Commit delta (auto-generated)

- fix(tests): make statusline and runner tests portable on windows (term-h65) (bc89c2a)
- chore(release): bump package version for next release (term-f0z) (f7b9095)
- fix(starship): raise scan timeout to stop directory scan warnings (term-f0z) (842befd)
- chore(beads): close restamp tracker issue (term-1r0) (1a0eba1)
- chore(basicly): restamp the install for the harness upgrade (term-1r0) (641428a)

## v0.4.3 - 2026-07-17

Delta: v0.4.2..v0.4.3

### Highlights

- **Refined status-line model icons.** The per-model glyphs now match the models' literary/musical naming: Opus is a music note (an "opus" is a musical work), and Fable gets a book. Haiku (leaf), Sonnet (pencil), and the unknown-model microchip fallback are unchanged. All icons stay in the portable Font Awesome v4 range, so they render on every Nerd Font version.
- Internal housekeeping, no effect on installed terminals: the packaged basicly install was re-stamped for the upstream 0.2.0 harness release.
- Re-apply with `terminal-setup --only config`; no WezTerm restart is needed — Claude Code re-reads the status line on its next render.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-zpj) (82dcaf0)
- feat(statusline): use music note for opus and add fable book icon (term-6m7) (e2078c5)
- chore(basicly): restamp the install for the harness upgrade (term-8kv) (f113ecb)

## v0.4.2 - 2026-07-17

Delta: v0.4.1..v0.4.2

### Highlights

- **The status line renders on every Nerd Font again.** The per-model icons now use classic Font Awesome v4 glyphs (Opus → star, Sonnet → pencil, Haiku → leaf) instead of Nerd Fonts v3-only codepoints. This fixes WezTerm's "no fonts contain glyphs for these codepoints `\u{ed62}`" notification that appeared when switching the model to Opus on machines whose bundled Nerd Font predates v3 — no font install or WezTerm update required. The default (unknown model) microchip glyph was already portable and is unchanged.
- Internal housekeeping, no effect on installed terminals: the packaged basicly install was refreshed.
- Re-apply with `terminal-setup --only config`; no WezTerm restart is needed — Claude Code re-reads the status line on its next render.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-trp) (90abe8f)
- fix(statusline): use portable font awesome v4 glyphs for model icons (term-86x) (eaf8c3f)
- chore(basicly): refresh the install at the third release (term-20c) (7e0b396)

## v0.4.1 - 2026-07-16

Delta: v0.4.0..v0.4.1

### Highlights

- **Mouse wheel scrolling is back to WezTerm defaults.** The custom 6-line wheel bindings and alternate-screen scroll speed introduced in v0.3.1 are removed: they showed no benefit in real agentic sessions and risked odd interactions with full-screen apps. The wheel now scrolls the standard 3 lines per tick everywhere.
- README usability: the quick install and config-only commands now lead the page, with a direct link to the latest release for pinned installs, and the keybinding tables match the v0.4.0 scheme (leader `Ctrl+Shift+Space`, jump-to-prompt on `Ctrl+Shift+Up/Down`, tmux pane navigation rows).
- Internal housekeeping, no effect on installed terminals: the packaged basicly harness converged to 0.1.2, the legacy CI workflows were retired in favor of the basicly gates, and the retired hand-rolled commit-message validator was deleted.
- Re-apply with `terminal-setup --only config` and restart WezTerm.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-mp4) (b176312)
- chore(basicly): restamp the install at the fixed release (term-pak) (a3732f0)
- docs(readme): put quick install first and fix stale keybindings (term-5ng) (a3f7815)
- chore(scripts): remove the retired commit message validator (term-v1v) (da60c82)
- ci(workflows): retire the legacy gates superseded by basicly-gates (term-hg3) (988a0dc)
- chore(basicly): converge the packaged harness to the newest release (term-hg3) (32815b9)
- chore(beads): close the wheel scroll removal (term-1q7) (22eb489)
- chore(wezterm): remove custom mouse wheel scroll speed (term-1q7) (2dee690)
- chore(beads): file the basicly update track (term-hg3) (ac50104)
- chore(beads): close the release track (term-k9e) (100972d)

## v0.4.0 - 2026-07-15

Delta: v0.3.1..v0.4.0

### Highlights

- **Breaking (muscle memory) — the WezTerm leader moved to `Ctrl+Shift+Space`.** Plain `Ctrl+Space` now reaches the tmux prefix from inside WezTerm (previously the leader shadowed it, making tmux bindings unusable). The no-confirmation `Ctrl+Shift+Q` quit binding is gone, vim-tmux-navigator is dropped so `Ctrl+L` works again (shell clear and Claude Code), and tmux pane navigation is prefix + `h/j/k/l` with repeatable resize on the capitals.
- **Jump between prompts in huge scrollback**: the deployed zshrc now emits OSC 133 prompt marks and OSC 7 cwd reports, so `Ctrl+Shift+Up/Down` jumps prompt-to-prompt in WezTerm and tab titles show the working directory for WSL panes again.
- **tmux copy reaches the system clipboard**: copy-mode `y` now uses OSC 52, crossing the WSL boundary to the Windows clipboard without clip.exe.
- Setup correctness fixes: the WSL guest home is resolved as `$HOME` instead of guessed from the Windows profile name (crashed when usernames differed), deployed files always get LF endings (the Windows-native status line was broken by CRLF), starship now installs into the WSL guest when setup runs from Windows, the VS Code fallback writes to a settings path VS Code actually reads, GitHub release lookups fail with a clear message when rate limited, and the Windows PATH update is idempotent and preserves `%VAR%` entries.
- New `--update` flag refreshes user-local tools (and Node) to their latest releases; plain re-runs keep the fast presence check. Failures now print the failing command's stderr instead of a bare traceback.
- Status line hardening: cost math and glyph rendering survive comma-decimal and non-UTF-8 locales, and a malformed `resets_at` no longer aborts the render. The template test suite grew from 127 to 153 tests.
- Internal: the repo adopted the packaged basicly harness (YAML catalog, beads tracker `term-*`, commit gates); no effect on installed terminals.
- Re-apply with `terminal-setup --only config`, restart WezTerm, and reload tmux (prefix + `r`).

### Commit delta (auto-generated)

- chore(release): bump package version for next release (term-k9e) (54fb20f)
- chore(beads): close the packaged basicly adoption (term-7xk) (53ed404)
- chore(beads): close the overlay trim track (term-m3a) (211a400)
- chore(overlay): trim fragment bodies so generated agent files fit the 8000 cap (term-m3a) (15f6130)
- chore(beads): record m3a filing and claim (term-m3a) (7cf0c3c)
- chore(harness): adopt packaged basicly install and migrate the overlay to yaml (term-7xk) (ed0efff)
- chore(beads): close the review remediation epic (2f20a82)
- docs(cheat-sheet): reflect the new keybinding scheme and navigation (971a3e2)
- test(cli): cover report probes and runner matrix and generated scripts (942f3d8)
- feat(cli): add update flag to refresh user-local tools on re-run (ce17bee)
- feat(cli): surface child stderr and clean errors on every exit path (9dbd925)
- docs(prerequisites): state the deliberate checksum omission for shellcheck (1db559f)
- fix(prerequisites): make the windows path update idempotent and lossless (39addd7)
- fix(configs): reject shell metacharacters in wsl terminal cwd (15b3c21)
- fix(cli): probe user-local bin in the host verification report (17ff6b9)
- fix(platform): fall back to a real vscode user settings path (9f40d31)
- fix(prerequisites): validate github release lookups before building urls (a6e7c3a)
- fix(prerequisites): install starship into the wsl guest from windows (057b792)
- chore(starship): raise command timeout for git metrics on large repos (8c1200f)
- fix(statusline): locale-proof number parsing and glyph slicing (30bdf80)
- fix(tmux): guard the tpm bootstrap with an install hint (a39bbe5)
- fix(zshrc): bind ss3 application-mode key variants and prefer micro (8e5edfb)
- feat(shell-integration): osc 7 and 133 marks with jump-to-prompt keys (6b4e65b)
- fix(tmux): copy selections to the system clipboard via osc 52 (9b1522e)
- fix(tmux): vim-style pane navigation without stealing root-table keys (e2f67aa)
- fix(wezterm): move leader off the tmux prefix and drop quit binding (12c326d)
- fix(configs): resolve wsl guest home from the distro not windows profile (3a72dce)
- fix(runner): force lf newlines when writing deployed files (ae9889d)
- chore(beads): init tracker and file 2026-07 review remediation epic (bf9bd83)
- chore(claude): forbid exit-code-masking pipes on state-changing commands (9d31183)

## v0.3.1 - 2026-07-15

Delta: v0.3.0..v0.3.1

### Highlights

- WezTerm no longer shows the "Unable to load a font specified in your font config" notification on startup. The config named fonts the setup never installs (MesloLGS Nerd Font Mono everywhere, Noto Sans Mono on Linux/WSL); it now names only fonts guaranteed to resolve. Nerd Font glyphs for starship and the status line still render via WezTerm's bundled Symbols Nerd Font Mono, and the visible font is unchanged (Consolas/Cascadia Mono on Windows, DejaVu Sans Mono on Linux).
- Mouse wheel scrolling is twice as fast: 6 lines per wheel tick instead of 3, in both the scrollback and alternate-screen apps. Full-screen apps that handle the wheel themselves (tmux, less) are unaffected.
- Re-apply with `terminal-setup --only config` and restart WezTerm.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (fa6bf1a)
- feat(wezterm): double mouse wheel scroll speed (2182a00)
- fix(wezterm): drop unresolvable fonts causing the startup warning toast (ce18f8d)

## v0.3.0 - 2026-07-15

Delta: v0.2.2..v0.3.0

### Highlights

- **Breaking — install default flipped to user-local.** Running with no flags now installs tools user-locally without admin rights (on Windows and inside WSL). `--user-install` is a deprecated no-op kept for compatibility; use the new `--system-install` for a system-wide install via apt/brew. Re-running the setup is still the update path.
- git-lfs and direnv now install user-locally in WSL (previously skipped in no-admin mode). The system-vs-user reconciliation also resolves apt ownership correctly when run from Windows, so it can offer to remove duplicate system copies instead of mislabeling them.
- Native Windows shells are first-class: the WezTerm launch menu gains an auto-detected Git Bash entry, and Starship is wired into PowerShell 7 (`$PROFILE`) and Git Bash, sharing one `~/.config/starship.toml`.
- The Claude Code status line is now installed for the Windows-native Claude too (not just WSL) and renders correctly there: a UTF-8-locale fix removes the mangled (`�`) gauges from Windows `jq`'s CRLF output, the build falls back to universal glyphs when no Nerd Font is present, and the git segment shows the repo name for Windows backslash paths.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (46077d5)
- fix(statusline): show repo name for windows backslash paths (b5f2dae)
- fix(setup): windows statusline glyphs and accurate no-sudo message (9f0357f)
- docs: align install docs with the user-local default (fc42bb2)
- feat(cli): default to user-local install with opt-in --system-install (4ce17bc)
- fix(statusline): force utf-8 locale under git bash on windows (ce08328)
- fix(setup): reconcile wsl tool ownership via apt from windows (f894b62)
- feat(setup): give windows-native shells starship and claude status line (2f422be)
- feat(setup): add user-local git-lfs and direnv installers (e8a90e4)
- feat(cli): add prompt level and refine install log markers (94b03df)
- refactor(runner): quiet read-only probe echo in install output (281ada2)
- feat(cli): make install output symbol-based and color-aware (46ac29e)
- docs(readme): consolidate setup instructions and fix config-file naming (3dfc793)
- refactor(cli): align setup flag names and group the help output (f932899)
- chore(scripts): remove unrelated wsl ubuntu upgrade script (2f3437f)
- feat(cli): add claude and config-only setup flags (4822511)
- feat(configs): install claude code status line during setup (9bf051e)
- chore(claude): adopt trusted-workstation permission model (5138e7a)
- ci: extend bandit gate to scan terminal-setup package (59a0840)
- fix(vscode): scope bandit task to first-party source like the gate (ab62b99)
- fix(vscode): use pythonpath env for basicly tasks (6fc0ca8)
- feat(scripts): add sync-basicly script and refresh vendored engine (e88bad1)
- chore: add claude code permission allowlist for repo gates (91b013d)
- refactor(basicly): adopt core catalog layout with vendored engine bridge (7c4e0b6)

## v0.2.2 - 2026-07-13

Delta: v0.2.1..v0.2.2

### Highlights

- All remaining tool downloads are now sha256-verified before installing: fzf, jq, and yq against their published checksum files, and the WezTerm Windows archive, WezTerm AppImage, and starship Windows archive against their `.sha256` release assets. (shellcheck publishes no checksum file; the uv/rustup vendor installers stay as-is by design.)
- The Windows verification report now probes the known install directories, so freshly installed WezTerm/starship show `OK` with a restart hint instead of `MISSING` before the PATH refresh.
- `wsl --install` now warns up front that administrator rights are required and fails with clear guidance instead of an opaque error.
- Docs refreshed: portable Windows installs and user-local mode documented as the default behavior, and the release runbook now covers the version bump and commit-message constraints.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (5dbc80c)
- docs: refresh install notes and release runbook (905090f)
- feat(setup): verify remaining downloads and improve reporting (acfe6c5)

## v0.2.1 - 2026-07-13

Delta: v0.2.0..v0.2.1

### Highlights

- Windows installs no longer use winget/MSI: WezTerm and starship always install from portable release archives into `%LOCALAPPDATA%\Programs\`, so the setup works without admin rights in every mode. Existing winget installs are still detected and kept.
- Node.js and lazygit downloads are now sha256-verified against the published checksum files before installing.
- `--no-sudo` is honored on native Linux/macOS hosts for CLI extras: package-manager installs are skipped with a warning and lazygit installs user-locally.
- Documented the managed Node runtime, the single-source `--user-install` model, and the versioned system-vs-user conflict report in the README and cheat sheet.

### Commit delta (auto-generated)

- chore(release): bump package version for next release (431aa46)
- docs: document node runtime and single-source install model (ac0e21f)
- feat(setup): portable windows installs with checksums and no-sudo extras (4d179e3)

## v0.2.0 - 2026-07-13

Delta: v0.1.0..v0.2.0

### Highlights

- Fixed the core Windows-to-WSL failure: WSL commands now run via `wsl --exec`, so the guest shell no longer expands variables inside install scripts (the "Unsupported OS" error). `--user-install` now implies no-sudo for WSL/Linux tools.
- Node.js is now installed and managed user-locally in WSL/Linux, matching the Windows major version; the setup report includes it.
- Single-source tool model: `--user-install` installs user-local copies even when a system copy exists, then reports each conflict with both versions and reconciles it. Removal is interactive by default, automatic with `--uninstall-system-versions`, or report-only with `--keep-system-versions`.
- More reliable Windows installs: WezTerm and starship install from release archives directly onto PATH, and setup templates are packaged into the wheel so `uvx` installs work.
- Safer runs: headless/no-TTY runs fail fast instead of hanging on hidden sudo prompts, and a failing VS Code extension install warns instead of aborting setup.
- Overhauled the terminal cheat sheet: full WezTerm and tmux shortcut reference, a modern CLI tool guide, click-to-copy commands, jump-to-section navigation, and a mobile-friendly responsive layout.
- Scoped the starship Kubernetes prompt segment to Kubernetes directories so it no longer implies a cluster connection everywhere.

### Commit delta (auto-generated)

- fix(setup): detect system tool copies shadowed by user-local ones (91c97f7)
- feat(setup): force user-local installs and show versions in conflict report (2202f85)
- feat(setup): report and reconcile system-vs-userlocal tool conflicts (a5c3f5e)
- feat(setup): install user-local nodejs matching windows major (cfc0536)
- feat(cheat-sheet): click-to-copy commands and header polish (9a1e93f)
- feat(cheat-sheet): full shortcut reference and smarter html page (a1e25b6)
- fix(setup): fail fast on headless sudo and honor skip-starship in wsl (d59519d)
- fix(config): scope starship kubernetes segment to k8s directories (432c926)
- fix(setup): use appimage fallback for wezterm when user-install is set (b090e00)
- fix(setup): warn instead of abort when vscode extension install fails (3f76158)
- fix(packaging): ship terminal-setup templates in the wheel (f7bc4fb)
- fix(setup): repair windows user installs and wsl tool detection (989178f)
- fix(setup): run wsl commands via --exec to stop shell re-parsing (4ab9173)
- chore(plans): move projector plans to basicly and keep wezterm status only (7c6c022)
- docs(skills): add release-process skill (516e074)

## v0.1.0 - 2026-07-12

Delta: initial..v0.1.0

### Highlights

- Added one-command user install via `uvx --from git+https://github.com/niksavis/terminal@main terminal-setup`.
- Improved setup safety and idempotency: installed tools are skipped, updates are user-confirmed (`y/n`), and lazygit release handling is version-aware.
- Expanded no-sudo and Windows-to-WSL behavior for more reliable installs in restricted environments.
- Strengthened WSL apt setup by cleaning legacy WezTerm sources before package operations.
- Added `--report-only` and clearer command reporting for verification without applying setup changes.
- Standardized local and CI quality gates: commit message checks, lint/type/security checks, and pre-push test enforcement.
- Added a changelog-driven release pipeline where release notes are sourced from this file by semantic tag.

### Commit delta (auto-generated)

- feat(release): add changelog-driven release pipeline (0a01a6a)
- ci(workflows): add yaml schema hints and tighten release vars (a9016a1)
- test: stabilize wsl detection mocks in hook-sensitive tests (3d1af61)
- fix(hooks): tighten commit message validation (5683ca5)
- chore: refresh release docs and remove unused verbose flag (d9dd765)
- ci: add quality gates workflow and hook parity (2359aa2)
- Refine setup guide and cheat sheet scope (8243d3b)
- Add report-only mode and improve command logging (2352e11)
- Fix lazygit installed version parsing (73c7d09)
- Fix lazygit tag parsing quoting (3091569)
- Make tool installs idempotent with update prompts (6c6bf40)
- Fix lazygit installer shell syntax for WSL sh (8213e6f)
- Enhance terminal UX and keep tooling agnostic (5ae26b0)
- Document safety rationale for legacy apt source cleanup (ea22711)
- Fix WSL apt cleanup script quoting in Windows flow (807bbd1)
- Remove legacy WezTerm apt source files in WSL preinstall step (d8bcd7d)
- Normalize WSL apt cleanup quoting (aab48d0)
- Remove stale fury.wez.dev apt sources before WSL updates (9f2fb19)
- Clean legacy WezTerm apt source during WSL apt installs (d922f09)
- Configure language-specific formatters for Python, TOML, and JSONC (196f578)
- Fix Windows-to-WSL no-sudo idempotent tool detection (073137a)
- Improve WSL no-sudo flow, keybindings, and prompt docs (97f5ab8)
- docs(skills): add skill-creator to basicly catalog (fb6baf9)
- chore(basicly): update generated manifest (7482aae)
- feat(skills): add and normalize terminal tool skills (3f92bf6)
- feat(basicly): add skill projection workflow infrastructure (86cecfb)
- fix(setup): batch apt installs and restore xh fallback (fe44727)
- fix(setup): remove xh from install baseline (78d9fb1)
- fix(scripts): run WSL upgrade commands as root (522f07e)
- docs(skill-creator): harden scope, guardrails, and validation (30692a5)
- feat(scripts): add WSL Ubuntu 26.04 upgrade script (1300fa3)
- fix: use robust fallback installers for unavailable apt tools (09bf755)
- feat: enforce agent-first tool baseline and add skill creator scaffold (5e70370)
- feat(setup): curate extra CLI tools and stabilize micro config test (0d99802)
- feat(setup): add micro config and useful CLI extras (45773a7)
- fix(zsh): guard bat theme export when theme is unavailable (da5eb5e)
- fix(vscode): pin Ruff binary path in workspace settings (bf429a8)
- Fix cross-platform Python interpreter settings (19d0055)
- feat(cheat-sheet): improve html rendering and add clear search (5e4e4eb)
- docs(readme): add quick cheat-sheet access links (ab64ed5)
- fix(ci): deploy pages on manual cheat-sheet runs (ecb8699)
- fix(basicly): normalize manifest paths for cross-platform CI (d1edb99)
- chore(basicly): refresh generated manifest (617f20f)
- ci(cheat-sheet): add manual workflow trigger (65e6716)
- ci(cheat-sheet): deploy github pages and refresh README (ceebd1d)
- fix(terminal-setup): stop deploying cheat sheet to user homes (207cdef)
- refactor(terminal-setup): move package to root and fix vscode cwd defaults (09ec2e0)
- fix(terminal-setup): harden WSL profiles and prompt UX (8ad5c60)
- feat(setup): interactive sudo, --user-install, and dry-run consistency (b582e28)
- feat: add terminal cheat sheet renderer, setup script, and automated HTML build (20e09f0)
- fix(basicly): make agent config files standalone (4d0cc68)
- feat(basicly): add source-of-truth projector for agent configs (9dfffe7)
- feat(devtools): add workspace tooling, git hooks, and plans (89aaab4)
