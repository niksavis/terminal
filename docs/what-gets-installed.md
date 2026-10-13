# What gets installed

This page lists each tool and each config file that the terminal setup installs. It tells you where each one goes on Windows, WSL, Linux and macOS. It also names the version that each install gives you. The facts on this page come from the code in [`terminal_setup/`](../terminal_setup/).

> **Windows needs WSL.** On Windows, setup installs the Linux tools into WSL 2 with an Ubuntu or Debian distro. Without WSL, setup stops at its first check and installs nothing. Set up WSL first with [Windows and WSL setup](windows-wsl-setup.md). That page also gives the prerequisites for each platform.

## Limits

Read these limits before you plan a roll-out:

- **Windows with no WSL gets no tools.** Setup checks its prerequisites first. When WSL is missing, setup stops and installs nothing. See [Windows without WSL](#windows-without-wsl).
- **The Windows host gets no command-line search tools.** Setup puts `rg`, `fd`, `jq` and the other command-line tools in WSL only. An agent that runs in PowerShell or Git Bash does not get them.
- **Setup needs `git`, `curl` and `wget` before it starts.** It does not install them. When one is missing, setup stops and names it.
- **Setup needs a package manager.** On Windows it needs `winget`, on macOS Homebrew, and on Linux `apt`, `pacman` or `dnf`. Setup uses `winget` only to find tools that are already installed.
- **lazygit needs `sudo` on macOS and on Linux outside WSL.** Setup installs lazygit into `/usr/local/bin` there. Add `--no-sudo` to install it into `~/.local/bin`.
- **Setup does not pin versions.** Most tools come from their latest release on the day that you run setup. Two runs on two days can install two versions. See [Versions](#versions).

## What each run sets up

The shell that starts setup decides what setup changes. A shell that runs on Windows makes a Windows run. A shell that runs inside WSL makes a WSL run. Windows Terminal and WezTerm only host a shell: the shell in the tab decides.

| You start setup in | Run type | Windows host | WSL distro |
| --- | --- | --- | --- |
| Windows PowerShell 5.1 (`powershell`) | Windows | ✓ | ✓ the default distro |
| PowerShell 7 (`pwsh`) | Windows | ✓ | ✓ the default distro |
| Command Prompt (`cmd`) | Windows | ✓ | ✓ the default distro |
| Git Bash | Windows | ✓ | ✓ the default distro |
| Windows Terminal or WezTerm, with a PowerShell, cmd or Git Bash tab | Windows | ✓ | ✓ the default distro |
| Windows Terminal or WezTerm, with an Ubuntu tab | WSL | ✗ | ✓ this distro |
| The Ubuntu app from the Start menu | WSL | ✗ | ✓ this distro |
| Any of the Windows shells, WSL missing | Windows | ✗ setup stops | ✗ setup stops |
| A Linux terminal (not WSL) | Linux | | |
| A macOS terminal | macOS | | |

### Start commands

| Shell | Command |
| --- | --- |
| PowerShell 5.1 or 7 | `irm https://raw.githubusercontent.com/niksavis/terminal/main/install.ps1 \| iex` |
| Command Prompt | `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/niksavis/terminal/main/install.ps1 \| iex"` |
| Git Bash | `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/niksavis/terminal/main/install.ps1 \| iex"` |
| Any Windows shell with uv | `uvx --refresh-package terminal --from https://github.com/niksavis/terminal/archive/main.zip terminal-setup` |
| WSL, Linux, macOS | `curl -LsSf https://raw.githubusercontent.com/niksavis/terminal/main/install.sh \| sh` |

On 2026-10-13, `--only check` ran on one Windows 11 machine with WSL from Command Prompt, from Git Bash with the PowerShell command, and from Git Bash with `uvx`. Each run printed `All prerequisites are satisfied.` and exited with code 0. `install.sh` is for WSL, Linux and macOS. It is not tested in Git Bash.

### A Windows run

Setup changes the Windows host and the default WSL distro in one run.

| Where | What setup installs | What setup writes |
| --- | --- | --- |
| Windows host | uv, Python 3.14, Node.js 26, WezTerm, starship, img-zoom, the agents named with `--agents`, the VS Code Remote - WSL extension when `code` is on PATH | `wezterm.lua`, `starship.toml`, the starship lines in the PowerShell 7 profile and in the Git Bash `.bashrc`, VS Code `settings.json`, and the Claude Code add-ons when `%USERPROFILE%\.claude` exists |
| Default WSL distro | zsh, tree, podman, bubblewrap, socat, podman-docker, all the command-line tools, uv, Python 3.14, Node.js 26, starship, img-zoom, the agents named with `--agents` | `.zshrc`, `.tmux.conf`, `starship.toml`, micro `settings.json`, the default shell, and the Claude Code add-ons when `~/.claude` exists |

The Windows host does not get `rg`, `fd`, `jq` or the other command-line tools. Setup does not install WezTerm in WSL on a Windows run. The WezTerm on Windows opens the WSL distro.

The result is the same from each Windows shell. The shell does not change which tools setup installs. Only these parts depend on what is present on Windows:

| Present on Windows | Then setup also |
| --- | --- |
| PowerShell 7 (`pwsh`) | adds the starship prompt to the PowerShell 7 profile |
| Git for Windows | adds the starship prompt to Git Bash, and the Claude Code status line on the Windows host |
| VS Code (`code` on PATH) | installs the Remote - WSL extension |

Command Prompt gets no starship prompt, because `cmd` has no prompt hook.

### A WSL run

Setup changes only the WSL distro that runs the shell. It does not change the Windows host.

| Where | What setup installs | What setup writes |
| --- | --- | --- |
| This WSL distro | the same as the WSL row of a Windows run. When WezTerm is missing in WSL, also the nightly WezTerm AppImage into `~/.local/bin` | the same as the WSL row of a Windows run, and `~/.config/wezterm/wezterm.lua` |
| Windows host | nothing | nothing |

After a WSL run, an agent that runs in PowerShell, cmd or Git Bash does not get img-zoom or the agents. Run setup from Windows to set up the Windows host.

### A Linux run

| What setup installs | What setup writes |
| --- | --- |
| zsh, tmux, all the command-line tools except podman, bubblewrap and socat, uv, Python 3.14, Node.js 26, WezTerm, starship, img-zoom, the agents named with `--agents` | `wezterm.lua`, `.zshrc`, `.tmux.conf`, `starship.toml`, micro `settings.json`, the default shell, and the Claude Code add-ons when `~/.claude` exists |

### A macOS run

| What setup installs | What setup writes |
| --- | --- |
| The same tools as a Linux run, through Homebrew | the same files as a Linux run |

Setup does not change VS Code settings on Linux or macOS.

## Versions

| Rule | Tools |
| --- | --- |
| Latest GitHub release on the day of the install, checked against its sha256 digest | WezTerm (Windows), starship, lazygit, fd, bat, ripgrep, fzf, jq, yq, shellcheck, git-lfs, direnv, xh, ast-grep, sd, just, delta, typos |
| Latest release from the vendor installer | uv, Claude Code |
| Latest release from the npm registry | GitHub Copilot CLI, OpenAI Codex |
| Python 3.14, the newest 3.14 patch that uv knows | Python |
| Node.js 26, the newest 26.x release on nodejs.org, checked against `SHASUMS256.txt` | Node.js |
| The version that the distro or Homebrew publishes | zsh, tmux, tree, podman, bubblewrap, socat (WSL), and the CLI tools on Linux outside WSL |
| Fixed in this repository | img-zoom 0.1.0, the basicly `cli-tools` skill at basicly v0.20.2 |

A rerun installs a missing tool and skips a current tool. For a tool that is older than its latest release, setup prints a line and changes nothing. Add `--update` to install the latest release. To see what is installed, run `--only report`. For a fixed version, pin the setup itself with a release tag, for example `TERMINAL_SETUP_REF=v0.12.7`. A pinned setup still installs the latest release of each tool.

## Tool inventory

### Terminal and shell

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| WezTerm | `wezterm` | A terminal program with tabs, panes and a launch menu. On Windows it opens the WSL distro by default. | The agent and the person share one terminal. Panes let the person watch the agent and run tests beside it. |
| zsh | `zsh` | The default login shell. Setup makes zsh the default shell with `chsh`. | One shell on each platform gives the agent the same syntax everywhere. |
| tmux | `tmux` | A terminal multiplexer. A session stays alive after the window closes. | A long agent run continues when the terminal closes. The person can attach to the session again. |
| starship | `starship` | The shell prompt. It shows the directory, the git branch, the git status and the runtime. | The person sees the branch and the state of the working tree before they approve an agent action. |
| micro settings | `micro` | Settings for the micro editor. Setup writes the settings only. It does not install micro. | When micro is present, `$EDITOR` is micro, a simple editor for a person who does not know vim. |

### Find, read and edit files

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| ripgrep | `rg` | A fast search of file contents. It obeys `.gitignore`. | The agent finds code faster and reads fewer unrelated files, so it spends fewer tokens. |
| fd | `fd` | A fast search of file names. It obeys `.gitignore`. | The agent lists the files that matter with a short command. |
| bat | `bat` | `cat` with line numbers and syntax colour. | The agent and the person read a file with line numbers to quote. |
| fzf | `fzf` | An interactive fuzzy finder for files and shell history. | The person finds a file or a command fast. Agents use it less. |
| tree | `tree` | Prints a directory as a tree. | The agent sees the layout of a repository in one command. |
| ast-grep | `ast-grep` | Searches and rewrites code by its syntax tree. | The agent changes many call sites safely. A text search cannot tell code from a comment or a string. |
| sd | `sd` | Find and replace with plain regular expressions. | The agent makes a replacement without the escape rules of `sed`, which differ between GNU and macOS. |
| typos | `typos` | Finds spelling mistakes in code and text. | The agent finds a misspelt name before review. |
| shellcheck | `shellcheck` | Finds bugs in shell scripts. | The agent checks a shell script before it runs it. |

### Structured data and HTTP

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| jq | `jq` | Reads and changes JSON. | The agent extracts one field from a large JSON output and reads fewer tokens. |
| yq | `yq` | Reads and changes YAML. This is the mikefarah `yq`. | The agent edits a YAML config without a mistake in the indentation. |
| xh | `xh` | Sends HTTP requests. It is a short form of `curl` for APIs. | The agent calls an API and reads a clean response. |
| curl | `curl` | Downloads files and calls HTTP endpoints. A prerequisite. | Setup and many installers need it. |
| wget | `wget` | Downloads files. A prerequisite. | Some scripts need it. |

### Git

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| git | `git` | Version control. A prerequisite. | The agent reads the history and commits its work. |
| lazygit | `lazygit` | A text user interface for git. | The person reviews and stages an agent change hunk by hunk. |
| delta | `delta` | Shows a git diff with syntax colour, side by side. | The person reads an agent diff fast. |
| git-lfs | `git-lfs` | Git Large File Storage, for large binary files. | The agent clones a repository that stores large files in LFS. |

### Runtimes, tasks and environment

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| uv | `uv`, `uvx` | Installs Python, Python packages and Python tools. | The agent runs a Python tool with `uvx` and changes no global state. |
| Python 3.14 | `python`, `python3` | The Python interpreter, installed by uv. | The agent runs Python scripts and tests. |
| Node.js 26 | `node`, `npm` | The JavaScript runtime and its package manager. | The agent runs JavaScript tools. Setup installs Copilot CLI and Codex with npm. |
| just | `just` | Runs project commands from a `justfile`. | The agent runs a named project command and does not guess a command line. |
| direnv | `direnv` | Loads environment variables when you enter a directory. | The agent gets the correct environment for each project. |

### Containers and sandbox (WSL only)

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| podman | `podman` | Runs containers without a daemon and without root. | The agent runs tests in a container. |
| podman-docker | `docker` | A `docker` command that runs podman. Setup installs it only when no Docker is present. | Scripts that call `docker` work. |
| bubblewrap | `bwrap` | A sandbox for a process. | The Claude Code sandbox (`/sandbox`) needs it on WSL2. |
| socat | `socat` | Relays data between sockets. | The Claude Code sandbox needs it on WSL2. |

### Agent tools

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| img-zoom | `img-zoom` | Crops a box from an image and makes it larger. It uses Pillow, and OpenCV where OpenCV publishes a build. | The agent reads small text in a screenshot or a drawing. |
| Claude Code | `claude` | Anthropic's coding agent. Only with `--agents claude` or `--agents all`. | The coding agent. |
| GitHub Copilot CLI | `copilot` | GitHub's coding agent. Only with `--agents copilot` or `--agents all`. | The coding agent. |
| OpenAI Codex | `codex` | OpenAI's coding agent. Only with `--agents codex` or `--agents all`. | The coding agent. |

### Claude Code add-ons

Setup writes these only when `~/.claude` exists. Add `--skip-claude` to skip them.

| Add-on | Where | What it is for |
| --- | --- | --- |
| Status line | `~/.claude/statusline.sh`, and the `statusLine` key in `~/.claude/settings.json` | Shows the model, the git state, the context use, the rate limits and the cost. On Windows it needs Git for Windows. |
| `img-zoom` skill | `~/.claude/skills/img-zoom/SKILL.md` | Tells Claude Code that `img-zoom` exists. |
| `cli-tools` skill | `~/.claude/skills/cli-tools/` | One reference file for each of 25 tools. Claude Code picks `rg`, `fd`, `jq` and the other tools in any repository. |

## Where each tool comes from

`~/.local/bin` means the user's own folder. It needs no administrator rights. In this table, "release" means the latest GitHub release, checked against its sha256 digest. "Vendor installer" means the installer script that the tool's vendor publishes.

| Tool | WSL distro | Windows host | Linux host (default) | macOS host |
| --- | --- | --- | --- | --- |
| WezTerm | ✗ from Windows. Inside WSL, when it is missing: the nightly AppImage into `~/.local/bin` | release zip into `%LOCALAPPDATA%\Programs\WezTerm` | apt (the WezTerm apt repository), pacman or dnf | Homebrew cask |
| starship | release into `~/.local/bin` (from Windows), vendor installer into `~/.local/bin` (inside WSL) | release zip into `%LOCALAPPDATA%\Programs\starship` | vendor installer into `~/.local/bin` | Homebrew |
| zsh, tree | apt, as root | ✗ | package manager | Homebrew |
| tmux | must be present: setup warns when it is missing | ✗ | package manager | Homebrew |
| git, curl, wget | must be present | ✗ | must be present | must be present |
| podman, bubblewrap, socat, podman-docker | apt, as root | ✗ | ✗ | ✗ |
| lazygit | release into `~/.local/bin` | ✗ | release into `/usr/local/bin`, with sudo | release into `/usr/local/bin`, with sudo |
| yq | release into `~/.local/bin` | ✗ | release into `~/.local/bin` | Homebrew |
| fd, bat, ripgrep, fzf, jq, shellcheck, git-lfs, direnv, xh, ast-grep, sd, just, delta, typos | release into `~/.local/bin` | ✗ | package manager. When apt has no package: release for ast-grep, just and typos, and the vendor installer for xh | Homebrew |
| uv | vendor installer into `~/.local/bin` | vendor installer (`install.ps1`) into `%USERPROFILE%\.local\bin` | package manager, else vendor installer | Homebrew |
| Python 3.14 | `uv python install` into `~/.local/bin` | `uv python install` into `%USERPROFILE%\.local\bin` | `uv python install` | `uv python install` |
| Node.js 26 | nodejs.org archive into `~/.local` | nodejs.org zip into `%LOCALAPPDATA%\Programs\nodejs` | nodejs.org archive into `~/.local` | nodejs.org archive into `~/.local` |
| img-zoom | `uv tool install` | `uv tool install` | `uv tool install` | `uv tool install` |
| Claude Code | vendor installer | vendor installer | vendor installer | vendor installer |
| Copilot CLI, Codex | `npm install -g` | `npm install -g` | `npm install -g` | `npm install -g` |
| VS Code Remote - WSL extension | | when `code` is on PATH | ✗ | ✗ |

On WSL and on Debian or Ubuntu, setup links `fd` to `fdfind` and `bat` to `batcat` when the distro names them so.

On Linux outside WSL, add `--no-sudo` to avoid sudo. Then setup skips the package-manager tools and installs only the tools that have a user installer.

## Tools that are already on Windows

Setup finds a Windows tool with the PATH. It does not ask winget which tool winget installed. Windows puts the machine PATH before the user PATH, so a machine-wide copy wins.

| Setup finds | WezTerm, starship | Python, Node.js | Claude Code, Copilot CLI, Codex |
| --- | --- | --- | --- |
| No copy | installs its copy | installs its copy | installs its copy, only with `--agents` |
| A machine-wide copy, for example in `C:\Program Files` | changes nothing. With `--update`, it prints an info line | prints an info line. When the version is too old, it prints a warning | prints an info line with `--update` |
| A copy in the user profile, for example from winget | keeps it | keeps it. When the version is too old, setup installs its own copy and warns that the old copy can come first on PATH | keeps it. With `--update`, it runs `<agent> update` on that copy |
| With `--update`, a user-profile copy that is older than the latest release | installs its own copy into `%LOCALAPPDATA%\Programs\<tool>`. A winget copy stays and can come first on PATH | upgrades Python only when uv manages it. Node.js: see the row above | runs `<agent> update` |

Setup never runs `winget uninstall`. To find which copy runs, use `Get-Command <tool> -All` in PowerShell. The first line is the copy that runs.

Setup does not install `rg`, `fd`, `jq`, `yq` or the other command-line tools on the Windows host. A copy from winget or another source stays as it is, and setup does not report it.

## Config files

When a config file differs from the template, setup keeps the old file as `<file>.terminal-setup.bak`. Put your own shell lines in `~/.zshrc.local`. Setup never writes that file.

| File | Where | What it does |
| --- | --- | --- |
| `wezterm.lua` | Windows: `%USERPROFILE%\.config\wezterm\`. Linux, macOS, WSL: `~/.config/wezterm/` | Key bindings, colours, and the WSL distro as the default tab on Windows |
| `.zshrc` | WSL, Linux, macOS home | History, key bindings, prompt marks, and hooks for starship, direnv and fzf |
| `.tmux.conf` | WSL, Linux, macOS home | The tmux prefix `Ctrl + Space` and pane key bindings |
| `starship.toml` | `~/.config/` in WSL, Linux and macOS. Also `%USERPROFILE%\.config\` on Windows | The prompt layout |
| `micro/settings.json` | `~/.config/micro/` in WSL, Linux and macOS | micro editor settings |
| PowerShell 7 profile | `$PROFILE.CurrentUserAllHosts`, only when `pwsh` is present | Starts starship in PowerShell 7 |
| `.bashrc`, `.bash_profile` | `%USERPROFILE%`, only when Git for Windows is present | Starts starship in Git Bash |
| VS Code `settings.json` | Windows only | Makes the WSL distro the default terminal in VS Code |
| Default shell | WSL, Linux, macOS | Setup runs `chsh` to make zsh the login shell. It needs your password, or root in unattended mode |

## Platform behaviour

### Windows, with WSL

Run from Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/niksavis/terminal/main/install.ps1 | iex
```

1. `install.ps1` installs uv into `%USERPROFILE%\.local\bin` when uv is missing.
2. uv downloads Python 3.14 and runs the setup.
3. Setup checks `winget`, WSL, the default distro, and `git`, `curl` and `wget` in that distro. When one is missing, setup stops.
4. Setup installs the WSL system packages as root: zsh, tree, podman, bubblewrap, socat, and podman-docker when no Docker is present. In an interactive run, setup asks first. With `--unattended`, it uses `wsl -u root` and asks for no password.
5. Setup installs the command-line tools, uv, Python, Node.js, starship and img-zoom into the WSL home.
6. Setup installs WezTerm, starship, Python, Node.js and img-zoom on the Windows host, in the user profile.
7. Setup installs the agents that you name with `--agents`, on both sides.
8. Setup writes the config files on both sides, and the VS Code settings.

Setup never runs as administrator. A tool that your organisation installed machine-wide stays as it is. See [Managed Windows machines](../README.md#managed-windows-machines).

### Windows without WSL

Setup installs nothing on a Windows machine with no WSL. It stops at the prerequisite check:

1. `install.ps1` installs uv into `%USERPROFILE%\.local\bin`.
2. uv downloads Python 3.14 into its own cache, and runs the setup.
3. Setup finds no WSL. It prints the line below and exits with code 1.

This output came from the setup code, with the platform set to Windows and WSL set to missing:

```text
✓ package-manager: found winget
⚠ wsl: WSL is not installed or not responsive; enable it via 'wsl --install'
✗ Some prerequisites are missing.
→ Install the missing items named above, then run: uvx --refresh-package terminal --from https://github.com/niksavis/terminal/archive/main.zip terminal-setup
```

The same stop occurs when the default distro is not Debian or Ubuntu. To continue, set up WSL with [Windows and WSL setup](windows-wsl-setup.md), then run the install again.

The setup has no mode for the Windows host alone. uv stays installed. To remove it, run `uv self uninstall`.

### Inside WSL

Run in the WSL shell:

```bash
curl -LsSf https://raw.githubusercontent.com/niksavis/terminal/main/install.sh | sh
```

Setup installs the same WSL tools as a run from Windows. It does not change the Windows host. When WezTerm is missing inside WSL, setup installs the nightly WezTerm AppImage into `~/.local/bin`. On Windows, start WezTerm from the Windows host.

The system packages need root. Setup asks once for your sudo password. With `--unattended` or `--no-sudo`, it prints the `apt` command for you to run.

### Linux

Setup installs on the host. It uses the package manager with `sudo` by default: `apt`, `pacman` or `dnf`. Setup accepts only a Debian or Ubuntu distro as the WSL distro. On a Linux host it also accepts Arch Linux (`pacman`) and Fedora (`dnf`). Only Ubuntu is tested.

The package manager installs the version that the distro publishes. That version can be older than the latest release. yq always comes from the mikefarah release, so each Linux host has the same `yq`.

### macOS

Setup installs with Homebrew. Homebrew must be present before you run setup. The macOS base system has no `wget`, so install it first with `brew install wget`. lazygit goes into `/usr/local/bin` and asks for your password. Add `--no-sudo` to put it into `~/.local/bin`.

## Check the result

Run the report after each install:

```bash
uvx --refresh-package terminal --from https://github.com/niksavis/terminal/archive/main.zip terminal-setup --only report
```

The report lists each tool with its path, and each config file. On Windows it lists the Windows host and the WSL distro.
