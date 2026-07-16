# Changelog

All notable user-facing changes are documented in this file by release tag.

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
