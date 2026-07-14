# terminal

Cross-platform terminal environment setup for developers using coding agents. Install WezTerm, WSL2 Ubuntu tooling, zsh, tmux, starship, and an agent-first CLI toolchain with one idempotent setup flow.

## Overview

If you use Claude Code, Copilot CLI, or similar agents, this repo gives you:

- A consistent terminal stack across Windows+WSL, Linux, and macOS.
- Better defaults for multitasking: WezTerm + tmux + zsh + starship.
- Fast CLI tools agents rely on: ripgrep, fd, bat, jq/yq, lazygit, uv, and more.
- Managed runtimes in WSL/Linux: Python via uv and Node.js (latest v24), matching the Windows versions.
- Safe re-runs: missing tools install, up-to-date tools skip, and updates prompt for `y/n`.
- Single-source tool ownership: `--user-install` keeps every managed tool in `~/.local`, reports conflicts with system copies (with versions), and can remove the duplicates.

## Quick install (users)

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.14+. On Windows, install WSL2 Ubuntu.

Use the latest setup directly from `main` (no clone required):

```bash
uvx --from git+https://github.com/niksavis/terminal@main terminal-setup
```

If you do not have admin rights on Windows:

```bash
uvx --from git+https://github.com/niksavis/terminal@main terminal-setup --user-install
```

For reproducible installs, use the pinned command shown on each GitHub release page.

## Contributor setup (required once after clone)

```bash
git clone https://github.com/niksavis/terminal.git
cd terminal
uv sync
npm install
uv run pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
uv run pre-commit run --all-files
uv run pytest tests/
```

Run the setup flow after your contributor environment is ready:

```bash
uv run python setup-terminal.py
```

Optional validation:

```bash
uv run python setup-terminal.py --only check
uv run python setup-terminal.py --dry-run
uv run python setup-terminal.py --only report
```

## What's here

- **Terminal setup** — Python package in [`terminal_setup/`](terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](terminal_setup/templates/wezterm.lua), [`.tmux.conf`](terminal_setup/templates/tmux.conf), [`.zshrc`](terminal_setup/templates/zshrc), [`starship.toml`](terminal_setup/templates/starship.toml), [`micro-settings.json`](terminal_setup/templates/micro-settings.json), and [`statusline.sh`](terminal_setup/templates/statusline.sh) (Claude Code status line).
- **Cheat sheet** — [Live HTML](https://niksavis.github.io/terminal/) and [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) source with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Agent skills (optional)** — many provided tools have companion skills in [`.claude/skills/`](.claude/skills/). For now, copy the skills you want into your own repository manually.

### Install with an AI coding agent

Copy and paste the prompt below into your coding agent (GitHub Copilot, Claude Code, etc.) after cloning this repo. The agent will run the setup for you and report what it changed.

```text
Install this repository's terminal setup from the current directory.

1. Ensure uv (https://docs.astral.sh/uv/) and Python 3.14+ are available. If missing, stop and tell me what to install.
2. Run `uv run python setup-terminal.py`.
3. If admin rights are unavailable on Windows, run `uv run python setup-terminal.py --user-install`.
4. If any sudo/password or y/n update prompt appears, pause and ask me.
5. When done, run `uv run python setup-terminal.py --only report` and summarize what was installed, skipped, and any manual next steps.
```

## Quick start

### Windows

After installation, start WezTerm from the Start menu or run:

```powershell
wezterm
```

WezTerm is configured to open WSL2 Ubuntu by default. The first time it starts, you will be in a zsh shell with tmux, starship, lazygit, direnv, just, fzf, and the extra CLI tools ready.

The default Starship prompt is single-line for readability and now includes project context modules (git state/metrics, common runtimes, and container context) before the prompt symbol.

Linux-style shortcuts are enabled in WezTerm: use `Ctrl + Shift + t` for a new tab, `Ctrl + Shift + c` to copy, and `Ctrl + Shift + v` to paste. To split a pane, press `Ctrl + Space` (leader) then `-` (vertical) or `backslash` (horizontal). To close a pane, press `Ctrl + Space` then `x`.

### WSL2 Ubuntu

If you prefer to work inside an existing WSL terminal, run the setup there too:

```bash
uv run python setup-terminal.py
```

This installs the same tools and configs directly on the WSL host. Then start a new zsh shell:

```bash
zsh
```

### Linux / macOS

Run the setup directly on the host:

```bash
uv run python setup-terminal.py
```

Then start WezTerm from your application launcher or run:

```bash
wezterm
```

## Daily controls

### WezTerm

| Action                    | Shortcut                                            |
| ------------------------- | --------------------------------------------------- |
| New tab                   | `Ctrl + Shift + t`                                  |
| Close tab                 | `Ctrl + Shift + w`                                  |
| Close window              | `Ctrl + Shift + q`                                  |
| Copy selection            | `Ctrl + Shift + c`                                  |
| Paste                     | `Ctrl + Shift + v`                                  |
| Search in scrollback      | `Ctrl + Shift + f`                                  |
| Quick-select URL/text     | `Ctrl + Shift + p`                                  |
| Launcher (profiles/tabs)  | `Ctrl + Shift + l`                                  |
| Copy with mouse           | Select text and release left button                 |
| Paste with mouse          | Right-click                                         |
| Split horizontal (direct) | `Ctrl + Alt + backslash`                            |
| Split vertical (direct)   | `Ctrl + Alt + -`                                    |
| Close pane (direct)       | `Ctrl + Alt + x`                                    |
| Next tab                  | `Ctrl + Tab`                                        |
| Previous tab              | `Ctrl + Shift + Tab`                                |
| Split vertical            | `Ctrl + Space` then `-` or `s`                      |
| Split horizontal          | `Ctrl + Space` then `backslash`, `pipe`, or `v`     |
| Move between panes        | `Shift + Ctrl + arrow` or `Ctrl + Space` then arrow |
| Rename tab                | `Ctrl + Space` then `,`                             |
| Switch workspace          | `Ctrl + Space` then `w`                             |
| Toggle fullscreen         | `Alt + Enter`                                       |
| Increase font size        | `Ctrl + Shift + =`                                  |
| Decrease font size        | `Ctrl + Shift + -`                                  |
| Reset font size           | `Ctrl + 0`                                          |
| Open config               | `Ctrl + Space` then `.`                             |

`Ctrl + Space` is a WezTerm leader key with a 3-second timeout. Press and release `Ctrl + Space`, then press the second key. It was chosen over `Ctrl + A` so the standard shell shortcuts `Ctrl + A` (beginning-of-line) and `Ctrl + E` (end-of-line) keep working.

### tmux

| Action           | Shortcut                 |
| ---------------- | ------------------------ |
| Prefix key       | `Ctrl + Space`           |
| New window       | `Ctrl + Space` then `c`  |
| Next window      | `Ctrl + Space` then `n`  |
| Previous window  | `Ctrl + Space` then `p`  |
| Reload config    | `Ctrl + Space` then `r`  |
| Split vertical   | `Ctrl + Space` then `\|` |
| Split horizontal | `Ctrl + Space` then `-`  |

See [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) for the full command reference.

WezTerm and tmux shortcuts in this README are project-defined keybindings from [`terminal_setup/templates/wezterm.lua`](terminal_setup/templates/wezterm.lua) and [`terminal_setup/templates/tmux.conf`](terminal_setup/templates/tmux.conf). They are intentionally included in the cheat sheet alongside native Linux commands.

## Starship prompt

The prompt is intentionally single-line and context-rich. It is configured in [`terminal_setup/templates/starship.toml`](terminal_setup/templates/starship.toml) and deployed to `~/.config/starship.toml`.

A typical prompt looks like:

```text
~/projects/terminal  main !? +12-3 py:v3.14.0 took 30s >
```

| Segment               | Meaning                                               |
| --------------------- | ----------------------------------------------------- |
| `~/projects/terminal` | Current directory (truncated to repo root)            |
| ` main`              | Git branch                                            |
| `!?`                  | Git status (`!` modified, `?` untracked, etc.)        |
| `+12-3`               | Git line metrics for staged/unstaged changes          |
| `py:v3.14.0`          | Runtime context for active project tools              |
| `took 30s`            | Duration of the last command (shown when over 500 ms) |
| `>`                   | Prompt character (red if the last command failed)     |
| `✦1`                  | Number of background jobs (only shown when present)   |

The prompt uses the Tokyo Night color palette and keeps all segments on one line for readability.

## Claude Code status line

When [Claude Code](https://claude.com/claude-code) is installed (`~/.claude` exists), the setup deploys a responsive status line to `~/.claude/statusline.sh` and registers it in `~/.claude/settings.json` (existing settings are preserved). It shows the model and reasoning effort, git repo/branch/state, gauges for context-window and 5-hour/weekly rate-limit usage (green → yellow → red), session cost with burn rate, and lines changed — using the same Tokyo Night palette as the prompt. Segments shorten and drop by priority as the terminal narrows.

Nerd Font icons are used by default (WezTerm ships a Nerd Font). Pass `--no-nerd-font` for the universal build that renders in any font, or `--skip-claude` to skip it. If Claude Code is not installed, this step is a no-op. To re-apply the configuration later — including an updated status line — without reinstalling packages, run `--only config`; an existing `~/.claude/statusline.sh` is overwritten (logged in the output), while other keys in `settings.json` are preserved.

## What gets installed

### Common baseline (all supported platforms)

- Core shell tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `lazygit`, `git-lfs`, `direnv`, `just`, `fzf`, `fd`/`fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- Runtimes (WSL/Linux/macOS): `node` (latest v24, user-local in `~/.local`)
- Config files: `wezterm.lua`, `.tmux.conf`, `.zshrc`, `starship.toml`, `micro settings.json`, and `~/.claude/statusline.sh` (Claude Code status line, when Claude Code is installed)

`lazygit` and `node` are installed from the latest upstream release archives (not distro/Homebrew package versions) and their downloads are sha256-verified against the published checksum files.

### Platform differences

#### Windows (PowerShell / Git Bash)

- Targets WSL2 Ubuntu as the primary shell environment
- Windows host installs: WezTerm and Starship from portable release archives into `%LOCALAPPDATA%\Programs\` (no admin rights or MSI needed; existing winget installs are detected and kept), plus the VS Code Remote - WSL extension
- WSL aliases: `fd` -> `fdfind`, `bat` -> `batcat`
- Config destinations: Windows `wezterm.lua` under `%USERPROFILE%\.config\wezterm\`, WSL files under `~`

#### Linux / macOS / WSL terminal

- Installs directly on the current host
- WezTerm install path: `apt` repo / `pacman` / `dnf` / Homebrew cask (platform-dependent)
- Starship install path: Linux install script or Homebrew on macOS
- Config destinations: all files under `~` on the host

## CLI options

```bash
uv run python setup-terminal.py --only check # verify prerequisites, then exit
uv run python setup-terminal.py --dry-run    # preview changes
uv run python setup-terminal.py --only config # re-apply all configs (incl. Claude status line); no package installs
uv run python setup-terminal.py --only report # print verification summary, then exit
uv run python setup-terminal.py --report     # run setup, then print verification summary
uv run python setup-terminal.py --skip-vscode # skip VS Code: settings/extensions
uv run python setup-terminal.py --skip-starship # skip starship prompt
uv run python setup-terminal.py --skip-claude # skip the Claude Code status line
uv run python setup-terminal.py --no-nerd-font # install the universal (no Nerd Font) status line
uv run python setup-terminal.py --user-install # user-local installs everywhere; no admin/sudo
uv run python setup-terminal.py --no-sudo    # avoid sudo prompts; skip missing base packages
uv run python setup-terminal.py --system-versions uninstall # remove system tool versions without prompting
uv run python setup-terminal.py --system-versions keep # keep system tool versions; only warn
uv run python setup-terminal.py --windows-terminal-cwd "D:\\Workspace" --wsl-terminal-cwd "$HOME/workspace" # optional user-specific cwd values
```

`--user-install` implies `--no-sudo` for tools inside WSL/Linux: every managed tool is installed user-locally under `~/.local`, even when a system copy already exists, so re-running the setup updates everything from one place.

After installing, the setup reconciles duplicates: it reports every tool present both in `~/.local/bin` and system-wide, with both versions (for example `lazygit: user-local 0.63.0 vs system 0.60.0`), then asks per tool whether to remove the system copy. `--system-versions uninstall` removes them all without prompting (requires sudo); `--system-versions keep` only reports. Headless runs never prompt or hang; they report and explain instead.

`--windows-terminal-cwd` and `--wsl-terminal-cwd` are optional user-specific values. No personal paths are hardcoded by default.

> **Note:** On Windows, WezTerm and Starship are always installed from portable release archives to `%LOCALAPPDATA%\Programs\` and the user PATH is updated (no admin rights or MSI needed). You must restart your terminal for the new PATH to take effect; until then the setup report marks them OK with a restart hint.

## Command-line editing

The zsh configuration uses Emacs-style readline shortcuts. These work in any terminal and are the fastest way to edit long commands without reaching for the mouse:

| Shortcut       | Action                                      |
| -------------- | ------------------------------------------- |
| `Ctrl + A`     | Move cursor to start of line                |
| `Ctrl + E`     | Move cursor to end of line                  |
| `Shift + Home` | Select from cursor to start of line         |
| `Shift + End`  | Select from cursor to end of line           |
| `Backspace`    | Delete selection or character before cursor |
| `Delete`       | Delete selection or character under cursor  |
| `Ctrl + U`     | Delete from cursor to start of line         |
| `Ctrl + K`     | Delete from cursor to end of line           |
| `Ctrl + W`     | Delete previous word                        |
| `Alt + D`      | Delete next word                            |
| `Ctrl + Y`     | Paste the last deleted text                 |
| `Ctrl + L`     | Clear screen                                |

`Shift + Home` and `Shift + End` are bound in zsh to create a selection region; once text is selected, `Backspace` or `Delete` removes it just like on Windows.

## Troubleshooting

### `xdg-desktop-portal` warning when starting WezTerm in WSL

You may see a warning like this on WSL2 Ubuntu:

```text
WARN window::os::x11::connection > Unable to resolve appearance using xdg-desktop-portal:
org.freedesktop.DBus.Error.ServiceUnknown: The name org.freedesktop.portal.Desktop was not
provided by any .service files
```

This is **harmless and expected**. The setup is intentionally lightweight: it targets a minimal WSL2 environment used as a virtual Linux machine inside Windows, not a full Linux desktop distribution. WezTerm hard-codes a dark color scheme so it does not need to query the desktop environment, but the underlying X11 connection still logs the missing portal service. Installing `xdg-desktop-portal` and its GTK/KDE backend would pull in GUI dependencies and a D-Bus session manager, which conflicts with the goal of keeping WSL lean. The warning does not affect WezTerm functionality.

## Development

After cloning, install all git hooks so commit format, lint, type checks, and tests run automatically:

```bash
uv sync
npm install
uv run pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

Run the test suite and pre-commit checks manually:

```bash
uv run pytest tests/
uv run python .scripts/git-hooks/pre-commit.py
```

## VS Code

Workspace settings, recommended extensions, tasks, and launch configs are committed in [`.vscode/`](.vscode/). Open the repo in VS Code and install the recommended extensions when prompted.

## License

[MIT](LICENSE)
