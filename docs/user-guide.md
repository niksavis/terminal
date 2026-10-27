# User guide

This guide is for a person who uses the terminal setup every day. To install, see the [README](../README.md). For the list of tools, see [What gets installed](what-gets-installed.md).

## Install options

The bootstrap script installs [uv](https://docs.astral.sh/uv/) user-locally when uv is missing, then runs the setup with Python 3.14. It needs no admin rights and no git.

Setup installs each of these only when it is missing: uv, Python 3.14 (with `uv python install`), Node.js 26, and the coding agents that you name with `--agents` (Claude Code, GitHub Copilot CLI, OpenAI Codex). It skips a Python 3.14 or newer and a Node.js 26 or newer that is already on PATH.

A rerun is safe. A missing tool installs, and a tool at its latest release is skipped. An older tool is reported, and `--update` installs the latest release. Only lazygit and the tools from a package manager (apt, Homebrew, pacman, dnf) ask `y/n` before an update. `--unattended` answers `no`.

The `irm | iex` form reads its options from `TERMINAL_SETUP_ARGS` instead, for example `$env:TERMINAL_SETUP_ARGS = '--unattended'`. The script clears the variable after it reads it, so the next run starts without options.

Each release carries its own copy of `install.ps1` and `install.sh`, and that copy installs that release. `releases/latest` always points to the newest release. To install one fixed release, use the commands on its [release page](https://github.com/niksavis/terminal/releases). `TERMINAL_SETUP_REF` overrides the release, for example `v0.19.0`.

## Install, update and check

Add an option to the install command. The commands below use the scriptblock form for PowerShell and `sh -s --` for WSL, Linux and macOS.

Re-apply only the configs (fast, no package installs), for example after a config update:

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --only config
```

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --only config
```

When `~/.zshrc`, `~/.tmux.conf`, `~/.config/starship.toml` or `~/.config/micro/settings.json` differs from the template, setup keeps the old file as `<file>.terminal-setup.bak` and names it in the output. Put your own shell lines in `~/.zshrc.local`, which setup never overwrites.

Update every user-local tool, uv, Python, Node.js, and the coding agents that you name with `--agents`, when they are older than their latest release (machine-wide Windows tools are left alone, see [Managed Windows machines](#managed-windows-machines)):

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --update
```

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --update
```

Check what is installed and configured:

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --only report
```

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --only report
```

Run from Windows, these commands set up the Windows host and the default WSL distro together.

With uv already installed, you can also run one fixed release directly, with no bootstrap script. Take the tag from the [release page](https://github.com/niksavis/terminal/releases), for example `uvx --from https://github.com/niksavis/terminal/archive/v0.19.0.zip terminal-setup --only report`. After a run, setup prints its follow-up commands in this form, with the tag that it ran.

## Unattended install for scripts and agents

`--unattended` never prompts. It answers `no` to every question, keeps the system versions of tools, and gives each command it runs an empty stdin, so a command that asks a question fails at once instead of waiting. The WSL system packages (zsh, tmux, tree, podman, bubblewrap, socat, libatomic1) need root: run from Windows, setup installs them with `wsl -u root`, which needs no password; inside WSL, it uses `sudo -n` when sudo needs no password, and otherwise prints the apt command for you to run once. Unattended mode cannot install WSL itself, because `wsl --install` needs administrator rights and asks for a new Linux user; setup stops and names the command. On Windows, unattended mode keeps every copy that winget installed, unless you also pass `--winget-versions replace`.

## Install with an AI coding agent

Copy and paste the prompt below into your coding agent (GitHub Copilot, Claude Code, etc.). No clone is needed. The agent runs the setup for you and reports what it changed.

```text
Install the terminal setup from https://github.com/niksavis/terminal without admin rights.

1. On Windows, first run `wsl -l -v` in PowerShell. If it lists no Ubuntu or Debian distro as the default, stop and tell me: WSL needs administrator rights, and setup installs nothing without it.
   Then run in PowerShell:
   $env:TERMINAL_SETUP_ARGS = '--unattended'; irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 | iex
   In WSL, Linux or macOS, run:
   curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --unattended
2. Add --agents all (or a list such as claude,codex) only if I asked for coding agents.
   Add --winget-versions replace only if I asked to replace the tools that winget installed.
3. If the output prints an apt command, show it to me: it needs my sudo password.
4. If the output names a machine-wide tool to update through IT or Software Center, tell me; do not try to change it.
5. When done, run the same install command again with --only report
   and summarize what was installed, skipped and failed, and any manual next steps.
```

## Managed Windows machines

Setup never runs as administrator. On Windows it changes only what is in your user profile (`%USERPROFILE%`). A tool that is installed machine-wide, for example from Software Center or Intune under `C:\Program Files`, is managed by your organisation, and setup leaves it as it is:

| Tool is | Setup does |
| --- | --- |
| missing | installs it in your user profile |
| installed by setup in your user profile | `--update` updates it: `uv python install --upgrade`, the Node.js zip, the WezTerm release zip, the tools in `%LOCALAPPDATA%\Programs\terminal-tools\bin`, and `claude update`, `copilot update`, `codex update` for the agents named in `--agents`. A running WezTerm does not block its update: setup renames the files in use and removes them on a later run. uv cannot replace itself while it runs setup, so `install.ps1` runs `uv self update` first when its options hold `--update` |
| installed by winget in your user profile | asks per tool, or follows `--winget-versions replace` or `keep`. See [Tools that are already on Windows](what-gets-installed.md#tools-that-are-already-on-windows) |
| machine-wide, new enough | prints one info line and changes nothing |
| machine-wide, too old | prints one warning with the version and the path: ask IT or use Software Center for a newer version |

Setup does not install a second copy beside a machine-wide one, because Windows puts the machine PATH before the user PATH, so the machine-wide copy always wins. If an agent update fails on Windows, setup names the command to run by hand, for example `codex update` in Windows PowerShell (`powershell.exe`).

## First start

### Windows

After installation, start WezTerm from the Start menu or run the command below. At the end of the install, setup prints where WezTerm is installed:

```powershell
wezterm
```

WezTerm is configured to open WSL2 Ubuntu by default. The first time it starts, you are in a zsh shell with starship, lazygit, direnv, just, fzf and the other command-line tools ready. Run `tmux` to start a session that stays alive after the window closes.

Press `Ctrl + Shift + l` — or right-click the `+` button in the tab bar, WezTerm's equivalent of the Windows Terminal new-tab dropdown — for the launch menu to switch shells: **Ubuntu-24.04 (WSL)** (named after your default WSL distro), **PowerShell** (pwsh 7), **Git Bash** (shown when Git for Windows is installed), and **Command Prompt**. Each entry opens as its own tab, so WSL, PowerShell, and Git Bash can run side by side; the three Windows-native profiles are pinned to WezTerm's `local` domain so they start on Windows rather than inside the WSL tab you launched them from. The setup wires the same Starship prompt into PowerShell 7 (`$PROFILE`) and Git Bash (`~/.bashrc`), sharing one `~/.config/starship.toml` on the Windows host, so those native shells match the WSL prompt. Command Prompt is left plain (cmd has no Starship prompt hook).

The default Starship prompt is single-line for readability. It shows the git branch and state, the common runtimes and the container context before the prompt symbol.

Linux-style shortcuts are enabled in WezTerm: use `Ctrl + Shift + t` for a new tab, `Ctrl + Shift + c` to copy, and `Ctrl + Shift + v` to paste. To split a pane, press `Ctrl + Shift + Space` (leader) then `-` (vertical) or `backslash` (horizontal). To close a pane, press `Ctrl + Shift + Space` then `x`.

### WSL2 Ubuntu

If you prefer to work inside an existing WSL terminal, run the setup there too:

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh
```

This installs the same tools and configs directly on the WSL host. Then start a new zsh shell:

```bash
zsh
```

### Linux / macOS

Run the setup directly on the host:

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh
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

See [`terminal-cheat-sheet.md`](../terminal-cheat-sheet.md) for the full command reference.

WezTerm and tmux shortcuts in this guide are project-defined keybindings from [`terminal_setup/templates/wezterm.lua`](../terminal_setup/templates/wezterm.lua) and [`terminal_setup/templates/tmux.conf`](../terminal_setup/templates/tmux.conf). They are intentionally included in the cheat sheet alongside native Linux commands.

### herdr

[herdr](https://herdr.dev/) keeps coding agents running in terminals that stay alive after the window closes. It shows whether each agent is working, blocked or idle. Install it with `--herdr`. To install herdr with all three coding agents and link them, add `--herdr --agents all` to the install command. Setup installs it in WSL, on Linux and on macOS, and not on the Windows host, because herdr on Windows has more limits.

Start it from the WezTerm launch menu, **herdr (WSL)** on Windows, or run `herdr` in a shell. herdr runs inside WezTerm and does not replace it. Your zsh and the starship prompt run in each herdr pane. herdr does the job of tmux for agent sessions, so use one of the two in a window, not both. The herdr prefix key is `Ctrl + b`. It does not clash with the tmux prefix `Ctrl + Space` or the WezTerm leader `Ctrl + Shift + Space`.

To show the state of an agent, herdr needs its integration. Setup installs it for each agent that you name with `--agents`, when you also add `--herdr`. The integration adds hooks to the agent config in `~/.claude`, `~/.codex` or `~/.copilot`. For an agent that you installed another way, run this once in the shell where herdr runs:

```bash
herdr integration install claude
herdr integration install copilot
herdr integration install codex
```

`herdr integration status` shows which integrations are installed. The setup report shows them too, as `herdr-claude`, `herdr-copilot` and `herdr-codex`.

zsh completes herdr commands with Tab. The first shell after a herdr install or update writes the completion file to `~/.cache/zsh/completions`.

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

## Starship prompt

Git line metrics are disabled to avoid a diff on each prompt. Git branch and
status information remain available.

The prompt is intentionally single-line and context-rich. It is configured in [`terminal_setup/templates/starship.toml`](../terminal_setup/templates/starship.toml) and deployed to `~/.config/starship.toml`.

A typical prompt looks like:

```text
~/projects/terminal  main !? py:v3.14.0 took 30s >
```

| Segment               | Meaning                                               |
| --------------------- | ----------------------------------------------------- |
| `~/projects/terminal` | Current directory (truncated to repo root)            |
| ` main`              | Git branch                                            |
| `!?`                  | Git status (`!` modified, `?` untracked, etc.)        |
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

Nerd Font icons are used by default (WezTerm ships a Nerd Font). Pass `--no-nerd-font` for the universal build, or `--skip-claude` to skip it. The universal build restricts itself to codepoints checked against the cmap of every font it can land in — Consolas, Cascadia Mono, and Lucida Console on Windows, DejaVu Sans Mono on Linux — so it renders in PowerShell and Git Bash rather than in a Nerd Font terminal only; a test asserts this over the rendered output, since a codepoint looking ordinary is no evidence a console font carries it. Two environment variables adjust it: `STATUSLINE_NERDFONT=1` or `0` forces the Nerd Font or the universal glyphs (the default is Nerd Font, and universal under Git Bash), and `STATUSLINE_WIDTH=<columns>` overrides the detected width. The script runs on bash 3.2 or newer, so the bash that ships with macOS works. If Claude Code is not installed, this step is a no-op. To re-apply the configuration later — including an updated status line — without reinstalling packages, run `--only config`; an existing `~/.claude/statusline.sh` is overwritten (logged in the output), while other keys in `settings.json` are preserved.

## CLI options

Add options to any setup command. Each command below runs as copied, without a clone and without git:

- PowerShell: `& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --dry-run`
- WSL, Linux, macOS: `curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --dry-run`
- Any shell with uv, one fixed release: `uvx --from https://github.com/niksavis/terminal/archive/v0.19.0.zip terminal-setup --dry-run` (take the tag from the [release page](https://github.com/niksavis/terminal/releases))
- In a clone: `uv run python setup-terminal.py --dry-run`

| Option | What it does |
| --- | --- |
| `--only check` | check the prerequisites, then exit |
| `--dry-run` | print each step and change nothing |
| `--only config` | re-apply all configs (also the Claude status line); install no packages |
| `--only report` | print the verification report, then exit. It shows each tool with its path and version, warns about Python older than 3.14 and Node.js older than v26, and lists the herdr integrations |
| `--report` | run setup, then print the verification report |
| `--unattended` | never ask a question; take the safe answer (for scripts and agents) |
| `--agents claude,codex` | also install these coding agents when missing; `all` installs all three. Setup never installs or updates an agent that you do not name |
| `--herdr` | also install herdr in WSL, on Linux and on macOS, and its integration for each agent named in `--agents`. With `--update`, setup updates herdr only with this option |
| `--update` | update every user-local tool, Python and Node.js that is out of date, and the agents named in `--agents` |
| `--skip-vscode` | skip the VS Code settings and extensions |
| `--skip-starship` | skip the starship prompt |
| `--skip-claude` | skip the Claude Code status line and skills |
| `--no-nerd-font` | install the universal (no Nerd Font) status line |
| `--no-sudo` | never use sudo; print the command for the packages that need it, in WSL and on a Linux host |
| `--system-install` | install system-wide through apt or brew (needs sudo or admin) |
| `--winget-versions replace` | Windows: replace each tool that winget installed in your user profile with the setup copy |
| `--winget-versions keep` | Windows: keep each winget copy; only report it |
| `--system-versions uninstall` | remove system tool versions without asking |
| `--system-versions keep` | keep system tool versions; only warn |
| `--windows-terminal-cwd PATH` | start directory for the VS Code terminal on Windows |
| `--wsl-terminal-cwd PATH` | start directory for WSL terminals and WezTerm |

The two directory options are optional and personal, so setup never sets them by itself. Quote a path with single quotes, because single quotes work the same in PowerShell and in bash, and write the WSL path in full. Replace `<your-linux-user>` with your Linux user name, which `whoami` prints in WSL:

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --windows-terminal-cwd 'D:\Workspace' --wsl-terminal-cwd '/home/<your-linux-user>/workspace'
```

`--windows-terminal-cwd` and `--wsl-terminal-cwd` are optional user-specific values. No personal paths are hardcoded by default.

## Troubleshooting

### WezTerm performance and stability defaults

Windows and WSL use the Software setting to retain the GPU-driver workaround.
Native Linux and macOS inherit WezTerm's renderer default. The template keeps
native tab titles, a small status footer and a scrollback limit of 10,000 lines.

The Kitty image protocol is disabled by default because older builds have known
image-parser crashes. Applications that require this protocol will not show those
images. The separate iTerm image protocol stays enabled.

The [investigation report](validation/terminal-responsiveness.md) records the
upstream reports, measured results, regression controls and remaining limits.
Confirm the runtime renderer in WezTerm's debug overlay before a renderer change.
A large Windows WSL working set alone does not establish memory exhaustion.

### Nerd Font icons

WezTerm draws Nerd Font icons with its built-in Symbols Nerd Font Mono, so you install no font. Each icon takes one column. To check it, run this in a WSL, Linux or macOS shell:

```bash
wezterm ls-fonts --text "$(printf '|\uf07b|')"
```

On Windows, run it in PowerShell:

```powershell
wezterm ls-fonts --text "|$([char]0xf07b)|"
```

The `\u{f07b}` line must show `cells=1` and `Symbols Nerd Font Mono`. Other terminals, such as the VS Code terminal or Windows Terminal, use their own font, and they can show the icon as an empty box.

### `xdg-desktop-portal` warning when starting WezTerm in WSL

You may see a warning like this on WSL2 Ubuntu:

```text
WARN window::os::x11::connection > Unable to resolve appearance using xdg-desktop-portal:
org.freedesktop.DBus.Error.ServiceUnknown: The name org.freedesktop.portal.Desktop was not
provided by any .service files
```

This is **harmless and expected**. The setup is intentionally lightweight: it targets a minimal WSL2 environment used as a virtual Linux machine inside Windows, not a full Linux desktop distribution. WezTerm hard-codes a dark color scheme so it does not need to query the desktop environment, but the underlying X11 connection still logs the missing portal service. Installing `xdg-desktop-portal` and its GTK/KDE backend would pull in GUI dependencies and a D-Bus session manager, which conflicts with the goal of keeping WSL lean. The warning does not affect WezTerm functionality.
