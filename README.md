# terminal

Cross-platform terminal environment setup. Install WezTerm, WSL2 Ubuntu tooling, zsh, tmux, starship, and a consistent set of CLI tools on every developer machine.

## What's here

- **Terminal setup** — Python package in [`.scripts/terminal_setup/`](.scripts/terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](.scripts/terminal_setup/templates/wezterm.lua), [`.tmux.conf`](.scripts/terminal_setup/templates/tmux.conf), [`.zshrc`](.scripts/terminal_setup/templates/zshrc), and [`starship.toml`](.scripts/terminal_setup/templates/starship.toml).
- **Cheat sheet** — [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Scripts** — cross-platform helpers in [`.scripts/`](.scripts/).
- **Tests** — workspace and setup tests in [`tests/`](tests/).

## Install guide

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

```bash
# Install dependencies and dev tools
uv sync

# Preview what the setup will do
uv run python .scripts/setup-terminal.py --dry-run

# Run the full setup
uv run python .scripts/setup-terminal.py
```

The setup is idempotent: running it again will only install missing tools and update configs.

## Quick start

### Windows

After installation, start WezTerm from the Start menu or run:

```powershell
wezterm
```

WezTerm is configured to open WSL2 Ubuntu by default. The first time it starts, you will be in a zsh shell with tmux, starship, fzf, and the extra CLI tools ready.

To open a new tab, press `Ctrl + t`. To split a pane, press `Ctrl + a` (leader) then `|` (vertical) or `-` (horizontal). To close a pane, press `Ctrl + a` then `x`.

### WSL2 Ubuntu

If you prefer to work inside an existing WSL terminal, run the setup there too:

```bash
uv run python .scripts/setup-terminal.py
```

This installs the same tools and configs directly on the WSL host. Then start a new zsh shell:

```bash
zsh
```

### Linux / macOS

Run the setup directly on the host:

```bash
uv run python .scripts/setup-terminal.py
```

Then start WezTerm from your application launcher or run:

```bash
wezterm
```

## Daily controls

### WezTerm

| Action | Shortcut |
| ------ | -------- |
| New tab | `Ctrl + t` |
| Close tab | `Ctrl + w` |
| Next tab | `Ctrl + Tab` |
| Previous tab | `Ctrl + Shift + Tab` |
| Split vertical | `Ctrl + a` then `\|` |
| Split horizontal | `Ctrl + a` then `-` |
| Move between panes | `Shift + Ctrl + arrow` or `Ctrl + a` then arrow |
| Rename tab | `Ctrl + a` then `,` |
| Open config | `Ctrl + a` then `.` |

### tmux

| Action | Shortcut |
| ------ | -------- |
| Prefix key | `Ctrl + a` |
| New window | `Ctrl + a` then `c` |
| Next window | `Ctrl + a` then `n` |
| Previous window | `Ctrl + a` then `p` |
| Split vertical | `Ctrl + a` then `\|` |
| Split horizontal | `Ctrl + a` then `-` |
| Reload config | `Ctrl + a` then `r` |

See [`terminal-cheat-sheet.md`](terminal-cheat-sheet.md) for the full command reference.

## What gets installed

### On Windows (PowerShell / Git Bash)

The setup targets WSL2 Ubuntu as the primary shell environment.

#### Windows host

- WezTerm via `winget`
- Starship prompt via `winget`
- VS Code: Remote - WSL extension

#### Inside WSL2 Ubuntu

- Core tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Extra CLI tools: `fzf`, `fd-find`, `bat`, `eza`, `zoxide`, `ripgrep`
- Aliases: `fd` -> `fdfind`, `bat` -> `batcat`

#### Configs deployed

- `wezterm.lua` -> `%USERPROFILE%\.config\wezterm\wezterm.lua`
- `.tmux.conf` -> WSL `~/.tmux.conf`
- `.zshrc` -> WSL `~/.zshrc`
- `starship.toml` -> WSL `~/.config/starship.toml`
- `terminal-cheat-sheet.md` -> `%USERPROFILE%\terminal-cheat-sheet.md` and WSL `~/terminal-cheat-sheet.md`

### On Linux / macOS / WSL Ubuntu terminal

The setup installs tools directly on the host.

- Core tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Extra CLI tools: `fzf`, `fd`/`fd-find`, `bat`, `eza`, `zoxide`, `ripgrep`
- WezTerm via `apt` repository, `pacman`, `dnf`, or Homebrew cask
- Starship prompt via install script (Linux) or Homebrew (macOS)

#### Configs deployed

- `wezterm.lua` -> `~/.config/wezterm/wezterm.lua`
- `.tmux.conf` -> `~/.tmux.conf`
- `.zshrc` -> `~/.zshrc`
- `starship.toml` -> `~/.config/starship.toml`
- `terminal-cheat-sheet.md` -> `~/terminal-cheat-sheet.md`

## CLI options

```bash
uv run python .scripts/setup-terminal.py --dry-run    # preview changes
uv run python .scripts/setup-terminal.py --check      # verify prerequisites only
uv run python .scripts/setup-terminal.py --skip-vscode # skip VS Code: settings/extensions
uv run python .scripts/setup-terminal.py --skip-starship # skip starship prompt
```

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
