# terminal

Cross-platform terminal environment setup. Install WezTerm, WSL2 Ubuntu tooling, zsh, tmux, starship, and an agent-first set of CLI tools on every developer machine.

## What's here

- **Terminal setup** — Python package in [`terminal_setup/`](terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](terminal_setup/templates/wezterm.lua), [`.tmux.conf`](terminal_setup/templates/tmux.conf), [`.zshrc`](terminal_setup/templates/zshrc), [`starship.toml`](terminal_setup/templates/starship.toml), and [`micro-settings.json`](terminal_setup/templates/micro-settings.json).
- **Cheat sheet** — [Live HTML](https://niksavis.github.io/terminal/) and [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) source with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Scaffolding scripts** — cross-platform harness helpers in [`.scripts/`](.scripts/).
- **Skill catalog** — basicly-managed tool skills in [`.basicly/skills/`](.basicly/skills/) projected to [`.claude/skills/`](.claude/skills/).
- **Tests** — workspace and setup tests in [`tests/`](tests/).

## Install guide

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

```bash
# Install dependencies and dev tools
uv sync

# Verify prerequisites only (no changes)
uv run python setup-terminal.py --check

# Preview what the setup will do
uv run python setup-terminal.py --dry-run

# Run the full setup
uv run python setup-terminal.py
```

The setup is idempotent: running it again installs missing tools, skips already up-to-date tools, and prompts before applying available tool updates.

### Install with an AI coding agent

Copy and paste the prompt below into your coding agent (GitHub Copilot, Claude Code, etc.) after cloning this repo. The agent will run the setup for you and report what it changed.

```text
I want to install the terminal environment defined in this repository.

Prerequisites: ensure uv (https://docs.astral.sh/uv/) and Python 3.14+ are available, and that WSL2 Ubuntu is installed if you are on Windows.

Run the setup idempotently:
1. Run `uv sync` to install dependencies.
2. Run `uv run python setup-terminal.py --dry-run` and show me the planned changes.
3. If the dry-run looks correct, run `uv run python setup-terminal.py` to apply the setup. If I do not have admin rights on Windows, use `uv run python setup-terminal.py --user-install` instead.
4. After the setup completes, verify that WezTerm, zsh, tmux, git, lazygit, git-lfs, direnv, just, starship, fzf, fd, bat, ripgrep, jq, yq, shellcheck, tree, xh, ast-grep, sd, delta, typos, and uv are available in the target environment (Windows WSL Ubuntu, Linux, or macOS as detected).
5. Report which tools were installed, which configs were deployed, and any manual steps I still need to take (for example, restarting WezTerm or setting zsh as the default shell).

Do not run destructive commands without explaining them first. If a prerequisite is missing, stop and tell me how to install it.
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

Create a workspace directory and clone a repository (choose your own path):

```bash
mkdir -p <workspace-dir>
cd <workspace-dir>
git clone https://github.com/niksavis/beads-blueprint.git
cd beads-blueprint
```

If you want to work on this repository after it is published:

```bash
cd <workspace-dir>
git clone https://github.com/niksavis/terminal.git
cd terminal
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

## What gets installed

### On Windows (PowerShell / Git Bash)

The setup targets WSL2 Ubuntu as the primary shell environment.

#### Windows host

- WezTerm via `winget`
- Starship prompt via `winget`
- VS Code: Remote - WSL extension

#### Inside WSL2 Ubuntu

- Core tools: `zsh`, `tmux`, `git`, `git-lfs`, `direnv`, `curl`, `wget`
- Agent-first CLI tools: `lazygit`, `just`, `fzf`, `fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- Aliases: `fd` -> `fdfind`, `bat` -> `batcat`

`lazygit` is installed from the latest upstream release archive (not from distro/Homebrew package versions) so `lazygit --version` reflects a current tagged release.

#### Configs deployed

- `wezterm.lua` -> `%USERPROFILE%\.config\wezterm\wezterm.lua`
- `.tmux.conf` -> WSL `~/.tmux.conf`
- `.zshrc` -> WSL `~/.zshrc`
- `starship.toml` -> WSL `~/.config/starship.toml`
- `settings.json` -> WSL `~/.config/micro/settings.json`

### On Linux / macOS / WSL Ubuntu terminal

The setup installs tools directly on the host.

- Core tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `lazygit`, `git-lfs`, `direnv`, `just`, `fzf`, `fd`/`fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- WezTerm via `apt` repository, `pacman`, `dnf`, or Homebrew cask
- Starship prompt via install script (Linux) or Homebrew (macOS)

`lazygit` is installed from the latest upstream release archive (not from distro/Homebrew package versions) so `lazygit --version` reflects a current tagged release.

#### Configs deployed

- `wezterm.lua` -> `~/.config/wezterm/wezterm.lua`
- `.tmux.conf` -> `~/.tmux.conf`
- `.zshrc` -> `~/.zshrc`
- `starship.toml` -> `~/.config/starship.toml`
- `settings.json` -> `~/.config/micro/settings.json`

## Cheat Sheet Publishing

- Live page: [https://niksavis.github.io/terminal/](https://niksavis.github.io/terminal/)
- Source: [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md)
- Build: [`.scripts/render-cheat-sheet.py`](.scripts/render-cheat-sheet.py) renders `terminal-cheat-sheet.html`
- CI/CD: [`.github/workflows/cheat-sheet.yml`](.github/workflows/cheat-sheet.yml) renders on each change to the cheat-sheet source and deploys the generated HTML to GitHub Pages on pushes to `main`
- One-time repo setting: enable **Settings > Pages > Source: GitHub Actions**

## CLI options

```bash
uv run python setup-terminal.py --dry-run    # preview changes
uv run python setup-terminal.py --check      # verify prerequisites only
uv run python setup-terminal.py --skip-vscode # skip VS Code: settings/extensions
uv run python setup-terminal.py --skip-starship # skip starship prompt
uv run python setup-terminal.py --user-install # install without admin rights (Windows)
uv run python setup-terminal.py --report     # print a post-setup verification summary
uv run python setup-terminal.py --windows-terminal-cwd "D:\\Workspace" --wsl-terminal-cwd "$HOME/workspace" # optional user-specific cwd values
```

`--windows-terminal-cwd` and `--wsl-terminal-cwd` are optional user-specific values. No personal paths are hardcoded by default.

> **Note:** When using `--user-install` on Windows, WezTerm and Starship are installed to `%LOCALAPPDATA%\Programs\` and the user PATH is updated. You must restart your terminal for the new PATH to take effect.

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

Install the git hooks to run lint, type checks, and tests automatically:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

Run the test suite and pre-commit checks manually:

```bash
uv run pytest tests/
uv run python .scripts/git-hooks/pre-commit.py

# Project and verify tool skills
PYTHONPATH=.basicly uv run python -m basicly.cli skills-build
PYTHONPATH=.basicly uv run python -m basicly.cli skills-check
```

## VS Code

Workspace settings, recommended extensions, tasks, and launch configs are committed in [`.vscode/`](.vscode/). Open the repo in VS Code: and install the recommended extensions when prompted.

## License

[MIT](LICENSE)
