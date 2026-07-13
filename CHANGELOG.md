# Changelog

All notable user-facing changes are documented in this file by release tag.

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
