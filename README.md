# terminal

Cross-platform terminal environment setup. Install WezTerm, WSL2 Ubuntu tooling, zsh, tmux, starship, and an agent-first set of CLI tools on every developer machine.

## What's here

- **Terminal setup** — Python package in [`terminal_setup/`](terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](terminal_setup/templates/wezterm.lua), [`.tmux.conf`](terminal_setup/templates/tmux.conf), [`.zshrc`](terminal_setup/templates/zshrc), [`starship.toml`](terminal_setup/templates/starship.toml), and [`micro-settings.json`](terminal_setup/templates/micro-settings.json).
- **Cheat sheet** — [Live HTML](https://niksavis.github.io/terminal/) and [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) source with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Scaffolding scripts** — cross-platform harness helpers in [`.scripts/`](.scripts/).
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

The setup is idempotent: running it again will only install missing tools and update configs.

### Install with an AI coding agent

Copy and paste the prompt below into your coding agent (GitHub Copilot, Claude Code, etc.) after cloning this repo. The agent will run the setup for you and report what it changed.

```text
I want to install the terminal environment defined in this repository.

Prerequisites: ensure uv (https://docs.astral.sh/uv/) and Python 3.14+ are available, and that WSL2 Ubuntu is installed if you are on Windows.

Run the setup idempotently:
1. Run `uv sync` to install dependencies.
2. Run `uv run python setup-terminal.py --dry-run` and show me the planned changes.
3. If the dry-run looks correct, run `uv run python setup-terminal.py` to apply the setup. If I do not have admin rights on Windows, use `uv run python setup-terminal.py --user-install` instead.
4. After the setup completes, verify that WezTerm, zsh, tmux, git, starship, fzf, fd, bat, ripgrep, jq, yq, shellcheck, tree, xh, ast-grep, sd, delta, typos, and uv are available in the target environment (Windows WSL Ubuntu, Linux, or macOS as detected).
5. Report which tools were installed, which configs were deployed, and any manual steps I still need to take (for example, restarting WezTerm or setting zsh as the default shell).

Do not run destructive commands without explaining them first. If a prerequisite is missing, stop and tell me how to install it.
```

## Quick start

### Windows

After installation, start WezTerm from the Start menu or run:

```powershell
wezterm
```

WezTerm is configured to open WSL2 Ubuntu by default. The first time it starts, you will be in a zsh shell with tmux, starship, fzf, and the extra CLI tools ready.

The default Starship prompt is intentionally single-line for readability: path, git, and status segments are shown before the prompt symbol on the same line.

Linux-style shortcuts are enabled in WezTerm: use `Ctrl + Shift + t` for a new tab, `Ctrl + Shift + c` to copy, and `Ctrl + Shift + v` to paste. To split a pane, press `Ctrl + a` (leader) then `-` (vertical) or `backslash` (horizontal). To close a pane, press `Ctrl + a` then `x`.

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

| Action                    | Shortcut                                        |
| ------------------------- | ----------------------------------------------- |
| New tab                   | `Ctrl + Shift + t`                              |
| Close tab                 | `Ctrl + Shift + w`                              |
| Close window              | `Ctrl + Shift + q`                              |
| Copy selection            | `Ctrl + Shift + c`                              |
| Paste                     | `Ctrl + Shift + v`                              |
| Split horizontal (direct) | `Ctrl + Alt + backslash`                        |
| Split vertical (direct)   | `Ctrl + Alt + -`                                |
| Close pane (direct)       | `Ctrl + Alt + x`                                |
| Next tab                  | `Ctrl + Tab`                                    |
| Previous tab              | `Ctrl + Shift + Tab`                            |
| Split vertical            | `Ctrl + a` then `-` or `s`                      |
| Split horizontal          | `Ctrl + a` then `backslash`, `pipe`, or `v`     |
| Move between panes        | `Shift + Ctrl + arrow` or `Ctrl + a` then arrow |
| Rename tab                | `Ctrl + a` then `,`                             |
| Toggle fullscreen         | `Alt + Enter`                                   |
| Increase font size        | `Ctrl + Shift + =`                              |
| Decrease font size        | `Ctrl + Shift + -`                              |
| Reset font size           | `Ctrl + 0`                                      |
| Open config               | `Ctrl + a` then `.`                             |

`Ctrl + a` is a WezTerm leader key with a 3-second timeout. Press and release `Ctrl + a`, then press the second key.

### tmux

| Action           | Shortcut             |
| ---------------- | -------------------- |
| Prefix key       | `Ctrl + a`           |
| New window       | `Ctrl + a` then `c`  |
| Next window      | `Ctrl + a` then `n`  |
| Previous window  | `Ctrl + a` then `p`  |
| Reload config    | `Ctrl + a` then `r`  |
| Split vertical   | `Ctrl + a` then `\|` |
| Split horizontal | `Ctrl + a` then `-`  |

See [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) for the full command reference.

WezTerm and tmux shortcuts in this README are project-defined keybindings from [`terminal_setup/templates/wezterm.lua`](terminal_setup/templates/wezterm.lua) and [`terminal_setup/templates/tmux.conf`](terminal_setup/templates/tmux.conf). They are intentionally included in the cheat sheet alongside native Linux commands.

## What gets installed

### On Windows (PowerShell / Git Bash)

The setup targets WSL2 Ubuntu as the primary shell environment.

#### Windows host

- WezTerm via `winget`
- Starship prompt via `winget`
- VS Code: Remote - WSL extension

#### Inside WSL2 Ubuntu

- Core tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `fzf`, `fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- Aliases: `fd` -> `fdfind`, `bat` -> `batcat`

#### Configs deployed

- `wezterm.lua` -> `%USERPROFILE%\.config\wezterm\wezterm.lua`
- `.tmux.conf` -> WSL `~/.tmux.conf`
- `.zshrc` -> WSL `~/.zshrc`
- `starship.toml` -> WSL `~/.config/starship.toml`
- `settings.json` -> WSL `~/.config/micro/settings.json`

### On Linux / macOS / WSL Ubuntu terminal

The setup installs tools directly on the host.

- Core tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `fzf`, `fd`/`fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- WezTerm via `apt` repository, `pacman`, `dnf`, or Homebrew cask
- Starship prompt via install script (Linux) or Homebrew (macOS)

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

## Development

Install the git hooks to run lint, type checks, and tests automatically:

```bash
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

Run the test suite and pre-commit checks manually:

```bash
uv run pytest tests/
uv run python .scripts/git-hooks/pre-commit.py
```

## VS Code

Workspace settings, recommended extensions, tasks, and launch configs are committed in [`.vscode/`](.vscode/). Open the repo in VS Code: and install the recommended extensions when prompted.

## License

[MIT](LICENSE)
