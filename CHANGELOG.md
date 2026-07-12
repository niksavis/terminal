# Changelog

All notable user-facing changes are documented in this file by release tag.

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
