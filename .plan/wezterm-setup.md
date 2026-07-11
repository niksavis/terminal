# WezTerm + WSL2 Terminal Setup Plan

## 1) Objective

Create a no-admin, crash-resistant terminal environment for long-running coding sessions on Windows 11 using WSL2 Ubuntu, with one consistent workflow across standalone WezTerm and the VS Code integrated terminal.

## 2) Scope

### In scope

- WezTerm installation paths (winget first, portable fallback).
- WSL2 Ubuntu shell/tooling setup (`zsh`, `tmux`, core CLI tools).
- Shared config templates for `wezterm.lua`, `.tmux.conf`, and `.zshrc`.
- VS Code integration via Remote - WSL.
- Terminal shortcuts cheat sheet (Linux commands + WezTerm/tmux/zsh productivity shortcuts).

### Out of scope

- Enabling WSL2 on machines where it is not already enabled (IT/admin action).
- Organization-specific policy exceptions and privileged system changes.

## 3) Deliverables

| #   | Deliverable                                                      | Location                                |
| --- | ---------------------------------------------------------------- | --------------------------------------- |
| 1   | Step-by-step setup guide for no-admin Windows + WSL2 workflow    | `.plan/wezterm-setup.md` or derived doc |
| 2   | Reusable config templates: `wezterm.lua`, `.tmux.conf`, `.zshrc` | `.config/` or repo templates folder     |
| 3   | Validation checklist for first-run verification                  | This plan, section 7                    |
| 4   | Terminal shortcut cheat sheet                                    | `.plan/wezterm-setup.md` or derived doc |

## 4) Assumptions and Constraints

- WSL2 is already enabled.
- `winget` is available on the Windows host.
- The user has `sudo` in the Ubuntu WSL2 guest.
- No Windows admin rights are required for the primary path.

## 5) Execution Plan

### Phase 1: Baseline and constraints

- [ ] Confirm WSL2 Ubuntu is installed and reachable.
- [ ] Confirm `winget` is available; document portable fallback if not.
- [ ] Define primary workflow (WezTerm + WSL2 Ubuntu) and fallback workflow (portable WezTerm ZIP).

### Phase 2: Installation workflow

#### Windows host

- [ ] Install WezTerm via `winget install wezterm`.
- [ ] Document portable ZIP install path for restricted environments.

#### WSL2 Ubuntu guest

- [ ] Update base packages.
- [ ] Install `zsh`, `tmux`, `git`, `curl`, `wget`.
- [ ] Optionally install and configure `starship` prompt.

### Phase 3: Configuration templates

- [ ] Create `wezterm.lua` template with:
  - WSL default domain (`WSL:Ubuntu`).
  - Performance defaults for long sessions.
  - Safe font fallback behavior.
- [ ] Create `.tmux.conf` template with:
  - Persistent/session-friendly defaults.
  - Mouse support and history tuning.
  - Extended keys support.
  - Optional plugin manager notes.
- [ ] Create `.zshrc` template with:
  - History behavior tuned for long-lived shells.
  - Optional starship initialization.

### Phase 4: VS Code integration

- [ ] Document Remote - WSL extension requirement.
- [ ] Set VS Code terminal profile to WSL Ubuntu.
- [ ] Confirm integrated terminal behavior matches WezTerm workflow.

### Phase 5: Shortcut cheat sheet

- [ ] Build a practical cheat sheet organized by use case:
  - Navigation, file operations, search, process, system commands.
  - Shell productivity shortcuts.
  - tmux daily controls.
  - WezTerm navigation and pane/tab controls.
- [ ] Mark risky commands clearly (for example recursive delete and force kill).

### Phase 6: Validation and handoff

- [ ] Validate startup and persistence:
  - Reopen WezTerm and restore tmux session flow.
  - Confirm VS Code integrated terminal connects to the same WSL environment.
- [ ] Validate performance baseline:
  - Expected memory footprint and scrollback behavior.
  - No blocking update checks during coding sessions.
- [ ] Publish final docs with troubleshooting notes.

## 6) Acceptance Criteria

- A user can follow the docs and complete setup without Windows admin rights.
- WezTerm and VS Code terminal both run inside the same WSL Ubuntu environment.
- tmux sessions persist across terminal restarts.
- The shortcut cheat sheet is complete, practical, and includes safety notes.

## 7) Validation Checklist

- [ ] WezTerm launches and defaults to WSL2 Ubuntu.
- [ ] `zsh` is the default shell in WSL2 Ubuntu.
- [ ] `tmux` is installed and a session can be created, detached, and reattached.
- [ ] VS Code Remote - WSL connects to the same Ubuntu environment.
- [ ] VS Code integrated terminal uses WSL Ubuntu by default.
- [ ] Config files are under version control or symlinked from a known location.
- [ ] Cheat sheet is accessible and covers daily navigation, tmux, and WezTerm shortcuts.

## 8) Risks and Mitigations

| Risk                                   | Mitigation                                                 |
| -------------------------------------- | ---------------------------------------------------------- |
| Missing WSL2 enablement                | Document IT prerequisite and stop point.                   |
| Corporate restrictions on winget/Store | Provide portable WezTerm path and manual validation steps. |
| Config drift between tools             | Keep one source of truth for shell/tmux config in WSL.     |

## 9) References

- [josean-dev/dev-environment-files](https://github.com/josean-dev/dev-environment-files/tree/main)
- [Essential Linux commands video](https://www.youtube.com/watch?v=F7rMWdB1s08)
