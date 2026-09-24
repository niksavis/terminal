# terminal

Cross-platform terminal environment setup for developers using coding agents. Install WezTerm, WSL2 Ubuntu tooling, zsh, tmux, starship, and an agent-first CLI toolchain with one idempotent setup flow.

## Quick install

Prerequisites: [uv](https://docs.astral.sh/uv/) and Python 3.14+. On Windows, install WSL2 Ubuntu.

Install everything (tools + configs) directly from `main` — no clone required:

```bash
uvx --from git+https://github.com/niksavis/terminal@main terminal-setup
```

Already installed? Re-apply only the configs (fast, no package installs) — for example after a config update:

```bash
uvx --from git+https://github.com/niksavis/terminal@main terminal-setup --only config
```

For a reproducible install pinned to a version, use the command shown on the [latest release](https://github.com/niksavis/terminal/releases/latest) page.

No admin rights are needed on Windows, WSL, or macOS: tools install into `~/.local` (or via Homebrew on macOS). Add `--system-install` for a system-wide install through apt/brew. On a native Linux host the default installs via apt and uses sudo.

## Overview

If you use Claude Code, Copilot CLI, or similar agents, this repo gives you:

- A consistent terminal stack across Windows+WSL, Linux, and macOS.
- Better defaults for multitasking: WezTerm + tmux + zsh + starship.
- Fast CLI tools agents rely on: ripgrep, fd, bat, jq/yq, lazygit, uv, and more.
- Managed runtimes in WSL/Linux: Python via uv and Node.js (latest v26). Windows-native Node is managed outside this setup, so the major is pinned here to keep both sides on one line — check `node --version` on each if you rely on them matching.
- Safe re-runs: missing tools install, up-to-date tools skip, and updates prompt for `y/n`.
- No admin needed by default: tools install user-locally into `~/.local`; the setup reports conflicts with any system copies (with versions) and can remove the duplicates. Use `--system-install` for a system-wide install.

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
2. Run `uv run python setup-terminal.py` (user-local, no admin required).
3. Only if a system-wide install is explicitly wanted, run `uv run python setup-terminal.py --system-install` (needs admin/sudo).
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

Press `Ctrl + Shift + l` — or right-click the `+` button in the tab bar, WezTerm's equivalent of the Windows Terminal new-tab dropdown — for the launch menu to switch shells: **Ubuntu (WSL)** (default), **PowerShell** (pwsh 7), **Git Bash** (shown when Git for Windows is installed), and **Command Prompt**. Each entry opens as its own tab, so WSL, PowerShell, and Git Bash can run side by side; the three Windows-native profiles are pinned to WezTerm's `local` domain so they start on Windows rather than inside the WSL tab you launched them from. The setup wires the same Starship prompt into PowerShell 7 (`$PROFILE`) and Git Bash (`~/.bashrc`), sharing one `~/.config/starship.toml` on the Windows host, so those native shells match the WSL prompt. Command Prompt is left plain (cmd has no Starship prompt hook).

The default Starship prompt is single-line for readability and now includes project context modules (git state/metrics, common runtimes, and container context) before the prompt symbol.

Linux-style shortcuts are enabled in WezTerm: use `Ctrl + Shift + t` for a new tab, `Ctrl + Shift + c` to copy, and `Ctrl + Shift + v` to paste. To split a pane, press `Ctrl + Shift + Space` (leader) then `-` (vertical) or `backslash` (horizontal). To close a pane, press `Ctrl + Shift + Space` then `x`.

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

| Action                    | Shortcut                                                                   |
| ------------------------- | -------------------------------------------------------------------------- |
| New tab                   | `Ctrl + Shift + t`                                                         |
| Close tab                 | `Ctrl + Shift + w`                                                         |
| Copy selection            | `Ctrl + Shift + c`                                                         |
| Paste                     | `Ctrl + Shift + v`                                                         |
| Search in scrollback      | `Ctrl + Shift + f`                                                         |
| Jump to previous prompt   | `Ctrl + Shift + Up`                                                        |
| Jump to next prompt       | `Ctrl + Shift + Down`                                                      |
| Quick-select URL/text     | `Ctrl + Shift + p`                                                         |
| Launcher (pick a shell)   | `Ctrl + Shift + l` or right-click the `+` button                           |
| Copy with mouse           | Select text and release left button                                        |
| Paste with mouse          | Right-click                                                                |
| Split horizontal (direct) | `Ctrl + Alt + backslash`                                                   |
| Split vertical (direct)   | `Ctrl + Alt + -`                                                           |
| Close pane (direct)       | `Ctrl + Alt + x`                                                           |
| Next tab                  | `Ctrl + Tab`                                                               |
| Previous tab              | `Ctrl + Shift + Tab`                                                       |
| Split vertical            | `Ctrl + Shift + Space` then `-` or `s`                                     |
| Split horizontal          | `Ctrl + Shift + Space` then `backslash`, `pipe`, or `v`                    |
| Move between panes        | `Ctrl + Shift + Left/Right` or `Ctrl + Shift + Space` then `h`/`j`/`k`/`l` |
| Zoom pane                 | `Ctrl + Shift + Space` then `z`                                            |
| Close pane                | `Ctrl + Shift + Space` then `x`                                            |
| Rename tab                | `Ctrl + Shift + Space` then `,`                                            |
| Switch workspace          | `Ctrl + Shift + Space` then `w`                                            |
| Toggle fullscreen         | `Alt + Enter`                                                              |
| Increase font size        | `Ctrl + Shift + =`                                                         |
| Decrease font size        | `Ctrl + Shift + -`                                                         |
| Reset font size           | `Ctrl + 0`                                                                 |
| Open config               | `Ctrl + Shift + Space` then `.`                                            |

`Ctrl + Shift + Space` is the WezTerm leader key with a 3-second timeout. Press and release `Ctrl + Shift + Space`, then press the second key. Plain `Ctrl + Space` is the tmux prefix, so the leader must not shadow it, and the readline shortcuts `Ctrl + A` (beginning-of-line) and `Ctrl + E` (end-of-line) stay untouched. Jump to previous/next prompt needs the OSC 133 prompt marks emitted by the deployed zshrc.

### tmux

| Action             | Shortcut                            |
| ------------------ | ----------------------------------- |
| Prefix key         | `Ctrl + Space`                      |
| New window         | `Ctrl + Space` then `c`             |
| Next window        | `Ctrl + Space` then `n`             |
| Previous window    | `Ctrl + Space` then `p`             |
| Reload config      | `Ctrl + Space` then `r`             |
| Split vertical     | `Ctrl + Space` then `\|`            |
| Split horizontal   | `Ctrl + Space` then `-`             |
| Move between panes | `Ctrl + Space` then `h`/`j`/`k`/`l` |
| Resize pane        | `Ctrl + Space` then `H`/`J`/`K`/`L` |
| Zoom pane          | `Ctrl + Space` then `m`             |

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

When [Claude Code](https://claude.com/claude-code) is installed (`~/.claude` exists), the setup deploys a responsive status line to `~/.claude/statusline.sh` and registers it in `~/.claude/settings.json` (existing settings are preserved). It shows the model and reasoning effort, git repo/branch/state, gauges for context-window and rate-limit usage (green → yellow → red), session cost with burn rate, and lines changed — using the same Tokyo Night palette as the prompt. Segments shorten and drop by priority as the terminal narrows.

### Reading the limit gauges

Claude Code can bill a single model against its own weekly window on top of the all-models one — the status line shows both, so `wk` and `fable` are two different limits rather than two views of one:

| Gauge       | Limit                                                                 | Source                                 |
| ----------- | --------------------------------------------------------------------- | -------------------------------------- |
| `5h 2%`     | The 5-hour session limit, shared by every model                       | Live, from the status line payload     |
| `wk 60%`    | The weekly limit across all models                                    | Live, from the status line payload     |
| `fable 83%` | The extra weekly limit for one model, labelled with that model's name | Sampled from Claude Code's usage cache |

The per-model gauge is the one to read with care, because it is a snapshot rather than a reading. Claude Code does not put that window on the status line's stdin, so it comes from the usage snapshot Claude Code caches in its own config file — and **only `/usage` and `/cost` write that cache**. Using the model it measures does not refresh it, so between those commands the figure is frozen at whatever it was when you last looked.

It therefore fades rather than lying. Within ten minutes of a refresh it renders in full colour like the live gauges; after that it drops to the dim colour, still readable but visibly no longer current; and once it passes the one-hour lifetime Claude Code gives that cache it disappears entirely. Run `/usage` to bring it back to full colour — that screen is also where the live figure always lives.

The two weekly windows share one segment, separated by a dim `·`, with the countdown stated once after both: they are the same week and reset within a microsecond of each other, so one reset covers the pair. With no per-model window the segment collapses to the all-models gauge alone.

The gauge is absent when no model has a window of its own, which is also what you will see if such a model later folds back into the all-models limit. Nothing needs re-applying for that; the segment simply stops appearing.

All four gauges share one form: five cells resolved to half a cell each, so they carry ten steps rather than five and 60% does not look like 70%. The half block is as fine as it goes — the eighth-width blocks that would give more steps are missing from Consolas and Lucida Console.

On Windows the status line is installed into **both** Claude Code homes so it looks the same wherever you open `claude`: the WSL `~/.claude` (Claude launched from WezTerm's Ubuntu shell) and the Windows-native `%USERPROFILE%\.claude` (Claude launched from PowerShell 7 or Git Bash). Windows-native Claude runs the status line through Git Bash, so that half is installed only when Git for Windows is present; the single bash script is shared across all of them (it strips the CR that Windows `jq` adds to its output).

Nerd Font icons are used by default (WezTerm ships a Nerd Font). Pass `--no-nerd-font` for the universal build, or `--skip-claude` to skip it. The universal build restricts itself to codepoints checked against the cmap of every font it can land in — Consolas, Cascadia Mono, and Lucida Console on Windows, DejaVu Sans Mono on Linux — so it renders in PowerShell and Git Bash rather than in a Nerd Font terminal only; a test asserts this over the rendered output, since a codepoint looking ordinary is no evidence a console font carries it. If Claude Code is not installed, this step is a no-op. To re-apply the configuration later — including an updated status line — without reinstalling packages, run `--only config`; an existing `~/.claude/statusline.sh` is overwritten (logged in the output), while other keys in `settings.json` are preserved.

## What gets installed

### Common baseline (all supported platforms)

- Core shell tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `lazygit`, `git-lfs`, `direnv`, `just`, `fzf`, `fd`/`fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- Agent image tool (WSL/Linux/macOS): `img-zoom`, installed with `uv tool install`. It crops a pixel box from an image file and magnifies it so an agent can read fine detail. Its Python also has Pillow and OpenCV for measuring scripts: `"$(uv tool dir)/img-zoom/bin/python"`
- Runtimes (WSL/Linux/macOS): `node` (latest v26, user-local in `~/.local`)
- Config files: `wezterm.lua`, `.tmux.conf`, `.zshrc`, `starship.toml`, micro `settings.json`, `~/.claude/statusline.sh` (Claude Code status line) and `~/.claude/skills/img-zoom/SKILL.md` (tells Claude Code that `img-zoom` exists), both only when Claude Code is installed and not skipped with `--skip-claude`

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
uv run python setup-terminal.py --system-install # install system-wide via apt/brew (needs sudo/admin)
uv run python setup-terminal.py --no-sudo    # force the user-local path; skip missing base packages
uv run python setup-terminal.py --system-versions uninstall # remove system tool versions without prompting
uv run python setup-terminal.py --system-versions keep # keep system tool versions; only warn
uv run python setup-terminal.py --windows-terminal-cwd "D:\\Workspace" --wsl-terminal-cwd "$HOME/workspace" # optional user-specific cwd values
```

By default the setup installs user-locally: on Windows and inside WSL every managed tool goes under `~/.local` without sudo, even when a system copy already exists, so re-running updates everything from one place. `--system-install` opts into the system-wide package-manager path (apt/brew, needs sudo/admin). On a native Linux host the default stays on apt (a user-local host install is not yet implemented there); macOS uses Homebrew, which needs no admin either way. The deprecated `--user-install` flag is a no-op kept for compatibility.

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

Contributor environment setup (dependencies and git hooks) is covered under [Contributor setup](#contributor-setup-required-once-after-clone). Once that is done, run the test suite and checks manually with:

```bash
uv run pytest tests/
uv run python .scripts/git-hooks/pre-commit.py
```

## VS Code

Workspace settings, recommended extensions, tasks, and launch configs are committed in [`.vscode/`](.vscode/). Open the repo in VS Code and install the recommended extensions when prompted.

## License

[MIT](LICENSE)
