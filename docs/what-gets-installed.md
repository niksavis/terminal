# What gets installed

This page lists each tool and each config file that the terminal setup installs. It tells you where each one goes on Windows, WSL, Linux and macOS. It also names the version that each install gives you. The facts on this page come from the code in [`terminal_setup/`](../terminal_setup/).

> **Windows needs WSL.** On Windows, setup installs the Linux tools into WSL 2 with an Ubuntu or Debian distro. Without WSL, setup stops at its first check and installs nothing. Set up WSL first with [Windows and WSL setup](windows-wsl-setup.md). That page also gives the prerequisites for each platform.

## Limits

Read these limits before you plan a roll-out:

- **Windows with no WSL gets no tools.** Setup checks its prerequisites first. When WSL is missing, setup stops and installs nothing. See [Windows without WSL](#windows-without-wsl).
- **Some tools are WSL-only.** zsh, tmux, tree, git-lfs, direnv, podman, bubblewrap and socat have no Windows build in setup. An agent in PowerShell or Git Bash gets the other command-line tools from `%LOCALAPPDATA%\Programs\terminal-tools\bin`.
- **Setup needs `git`, `curl` and `wget` before it starts.** It does not install them. When one is missing, setup stops and names it.
- **Setup needs a package manager outside Windows.** On macOS it needs Homebrew, and on Linux `apt`, `pacman` or `dnf`. On Windows, `winget` is optional. Setup uses `winget` only to find tools that are already installed.
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
| PowerShell 5.1 or 7 | `irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 \| iex` |
| Command Prompt | `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 \| iex"` |
| Git Bash | `powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 \| iex"` |
| Any shell with uv, one fixed release | `uvx --from https://github.com/niksavis/terminal/archive/v0.19.1.zip terminal-setup`, with the tag from the release page |
| WSL, Linux, macOS | `curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh \| sh` |

On 2026-10-13, `--only check` ran with the earlier `main` form of these commands on one Windows 11 machine with WSL from Command Prompt, from Git Bash with the PowerShell command, and from Git Bash with `uvx`. Each run printed `All prerequisites are satisfied.` and exited with code 0. `install.sh` is for WSL, Linux and macOS. It is not tested in Git Bash.

### A Windows run

Setup changes the Windows host and the default WSL distro in one run.

| Where | What setup installs | What setup writes |
| --- | --- | --- |
| Windows host | uv, Python 3.14, Node.js 26, WezTerm, img-zoom, and into `%LOCALAPPDATA%\Programs\terminal-tools\bin`: starship, rg, fd, bat, fzf, jq, yq, xh, ast-grep, sd, typos, shellcheck, lazygit, delta, just. Also the agents named with `--agents`, the VS Code Remote - WSL extension when `code` is on PATH | `wezterm.lua`, `starship.toml`, the starship lines in the PowerShell 7 profile and in the Git Bash `.bashrc`, VS Code `settings.json`, and the Claude Code add-ons when `%USERPROFILE%\.claude` exists |
| Default WSL distro | zsh, tmux, tree, podman, bubblewrap, socat, libatomic1, podman-docker, all the command-line tools, uv, Python 3.14, Node.js 26, starship, img-zoom, the agents named with `--agents` | `.zshrc`, `.tmux.conf`, `starship.toml`, micro `settings.json`, the default shell, and the Claude Code add-ons when `~/.claude` exists |

The Windows host does not get zsh, tmux, tree, git-lfs or direnv. Setup does not install WezTerm in WSL on a Windows run. The WezTerm on Windows opens the WSL distro.

Setup adds these folders to your Windows user PATH:

- `%LOCALAPPDATA%\Programs\terminal-tools\bin`, for starship and the command-line tools
- `%LOCALAPPDATA%\Programs\WezTerm`, when setup installs WezTerm there
- `%LOCALAPPDATA%\Programs\nodejs`, for Node.js
- `%USERPROFILE%\.local\bin`, for uv, Python and Claude Code
- the folder that `uv tool dir --bin` prints, for img-zoom

WezTerm gets an entry in the Start menu when setup installs it in `%LOCALAPPDATA%\Programs\WezTerm`. At the end of the run, setup prints where WezTerm is installed.

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

After a WSL run, an agent that runs in PowerShell, cmd or Git Bash does not get the Windows tools. At the end of a WSL run, setup prints the PowerShell command that sets up the Windows host.

### A Linux run

| What setup installs | What setup writes |
| --- | --- |
| zsh, tmux, all the command-line tools except podman, bubblewrap and socat, uv, Python 3.14, Node.js 26, WezTerm, starship, img-zoom, the agents named with `--agents` | `wezterm.lua`, `.zshrc`, `.tmux.conf`, `starship.toml`, micro `settings.json`, the default shell, and the Claude Code add-ons when `~/.claude` exists |

### A macOS run

| What setup installs | What setup writes |
| --- | --- |
| The same tools as a Linux run. Most come from Homebrew. Node.js comes from the nodejs.org archive into `~/.local`. lazygit comes from its release into `/usr/local/bin`, with sudo. uv and Python go into `~/.local/bin` | the same files as a Linux run |

Setup does not change VS Code settings on Linux or macOS.

## Versions

| Rule | Tools |
| --- | --- |
| Latest GitHub release on the day of the install, checked against its sha256 digest | WezTerm (Windows), herdr (WSL, Linux), starship, lazygit, fd, bat, ripgrep, fzf, jq, yq, shellcheck, git-lfs, direnv, xh, ast-grep, sd, just, delta, typos |
| Latest release from the vendor installer | uv, Claude Code, OpenAI Codex, GitHub Copilot CLI (WSL, Linux, macOS) |
| Latest release from the npm registry | GitHub Copilot CLI on Windows |
| Python 3.14, the newest 3.14 patch that uv knows | Python |
| Node.js 26, the newest 26.x release on nodejs.org, checked against `SHASUMS256.txt` | Node.js |
| The version that the distro or Homebrew publishes | zsh, tmux, tree, podman, bubblewrap, socat, libatomic1 (WSL), and the CLI tools on Linux outside WSL |
| Fixed in this repository | img-zoom 0.1.0, the basicly `cli-tools` skill from the published basicly v0.32.0 wheel |

A rerun installs a missing tool and skips a current tool. For a tool that is older than its latest release, setup prints a line and changes nothing. Add `--update` to install the latest release. To see what is installed, run `--only report`. For a fixed version, pin the setup itself with a release tag, for example `TERMINAL_SETUP_REF=v0.19.1`. A pinned setup still installs the latest release of each tool.

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
| Node.js 26 | `node`, `npm` | The JavaScript runtime and its package manager. | The agent runs JavaScript tools. On Windows, setup installs Copilot CLI with npm. |
| just | `just` | Runs project commands from a `justfile`. | The agent runs a named project command and does not guess a command line. |
| direnv | `direnv` | Loads environment variables when you enter a directory. | The agent gets the correct environment for each project. |

### Containers and sandbox (WSL only)

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| podman | `podman` | Runs containers without a daemon and without root. | The agent runs tests in a container. |
| podman-docker | `docker` | A `docker` command that runs podman. Setup installs it only when no Docker is present. | Scripts that call `docker` work. |
| bubblewrap | `bwrap` | A sandbox for a process. | The Claude Code sandbox (`/sandbox`) needs it on WSL2. |
| socat | `socat` | Relays data between sockets. | The Claude Code sandbox needs it on WSL2. |
| libatomic1 | (a library) | A runtime library. Node.js 26 needs it on Linux, and a fresh WSL Ubuntu does not have it. | Node.js, Copilot CLI and Codex start in WSL. |

### Agent tools

| Tool | Command | What it is for | How a coding agent benefits |
| --- | --- | --- | --- |
| img-zoom | `img-zoom` | Crops a box from an image and makes it larger. It uses Pillow, and OpenCV where OpenCV publishes a build. | The agent reads small text in a screenshot or a drawing. |
| Claude Code | `claude` | Anthropic's coding agent. Only with `--agents claude` or `--agents all`. | The coding agent. |
| GitHub Copilot CLI | `copilot` | GitHub's coding agent. Only with `--agents copilot` or `--agents all`. | The coding agent. |
| OpenAI Codex | `codex` | OpenAI's coding agent. Only with `--agents codex` or `--agents all`. | The coding agent. |
| herdr | `herdr` | Keeps coding agents running in terminals that stay alive after the window closes. It shows whether each agent is working, blocked or idle. Only with `--herdr`. | The person starts several agents, closes the window, and finds them again with their state. |

### Claude Code add-ons

Setup writes these only when `~/.claude` exists. Add `--skip-claude` to skip them.

| Add-on | Where | What it is for |
| --- | --- | --- |
| Status line | `~/.claude/statusline.sh`, and the `statusLine` key in `~/.claude/settings.json` | Shows the model, the git state, the context use, the rate limits and the cost. On Windows it needs Git for Windows. In WSL, Linux and macOS, setup needs `jq` to write the `statusLine` key. It finds the `jq` that it installs in `~/.local/bin`. Without `jq`, setup copies only the script and prints a warning. |
| `img-zoom` skill | `~/.claude/skills/img-zoom/SKILL.md` | Tells Claude Code that `img-zoom` exists. |
| `cli-tools` skill | `~/.claude/skills/cli-tools/` | One reference file for each of 25 tools. Claude Code picks `rg`, `fd`, `jq` and the other tools in any repository. |

## Where each tool comes from

`~/.local/bin` means the user's own folder. It needs no administrator rights. In this table, "release" means the latest GitHub release, checked against its sha256 digest. "Vendor installer" means the installer script that the tool's vendor publishes.

| Tool | WSL distro | Windows host | Linux host (default) | macOS host |
| --- | --- | --- | --- | --- |
| WezTerm | ✗ from Windows. Inside WSL, when it is missing: the nightly AppImage into `~/.local/bin`. With `--system-install`: the WezTerm apt repository | release zip into `%LOCALAPPDATA%\Programs\WezTerm`, with a WezTerm entry in the Start menu. Skipped when `wezterm` is on PATH, in `C:\Program Files\WezTerm`, or installed by winget | apt (the WezTerm apt repository), pacman or dnf. With `--no-sudo`, or when the apt repository fails: the nightly AppImage into `~/.local/bin` | Homebrew cask |
| starship | release into `~/.local/bin` (from Windows), vendor installer into `~/.local/bin` (inside WSL) | release into `%LOCALAPPDATA%\Programs\terminal-tools\bin` | vendor installer into `~/.local/bin` | Homebrew |
| zsh, tmux, tree | apt, as root | ✗ | package manager | Homebrew |
| git, curl, wget | must be present | ✗ | must be present | must be present |
| podman, bubblewrap, socat, libatomic1, podman-docker | apt, as root | ✗ | ✗ | ✗ |
| lazygit | release into `~/.local/bin` | release into `%LOCALAPPDATA%\Programs\terminal-tools\bin` | release into `/usr/local/bin`, with sudo | release into `/usr/local/bin`, with sudo |
| yq | release into `~/.local/bin` | release into `%LOCALAPPDATA%\Programs\terminal-tools\bin` | release into `~/.local/bin` | Homebrew |
| fd, bat, ripgrep, fzf, jq, shellcheck, xh, ast-grep, sd, just, delta, typos | release into `~/.local/bin` | release into `%LOCALAPPDATA%\Programs\terminal-tools\bin` | package manager. When apt has no package: release for ast-grep, just, typos and xh | Homebrew |
| git-lfs, direnv | release into `~/.local/bin` | ✗ | package manager | Homebrew |
| uv | vendor installer into `~/.local/bin` | vendor installer (`install.ps1`) into `%USERPROFILE%\.local\bin` | package manager, else vendor installer | Homebrew |
| Python 3.14 | `uv python install` into `~/.local/bin` | `uv python install` into `%USERPROFILE%\.local\bin` | `uv python install` | `uv python install` |
| Node.js 26 | nodejs.org archive into `~/.local` | nodejs.org zip into `%LOCALAPPDATA%\Programs\nodejs` | nodejs.org archive into `~/.local` | nodejs.org archive into `~/.local` |
| img-zoom | `uv tool install` | `uv tool install` | `uv tool install` | `uv tool install` |
| Claude Code | vendor installer into `~/.local/bin` | vendor installer into `%USERPROFILE%\.local\bin` | vendor installer into `~/.local/bin` | vendor installer into `~/.local/bin` |
| Codex | vendor installer (`chatgpt.com/codex/install.sh`) into `~/.local/bin` | vendor installer (`chatgpt.com/codex/install.ps1`) into `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin` | vendor installer into `~/.local/bin` | vendor installer into `~/.local/bin` |
| Copilot CLI | vendor installer (`gh.io/copilot-install`) into `~/.local/bin` | `npm install -g @github/copilot` into the Node.js folder, `%LOCALAPPDATA%\Programs\nodejs` when setup installed Node.js | vendor installer into `~/.local/bin` | vendor installer into `~/.local/bin` |
| VS Code Remote - WSL extension | | when `code` is on PATH | ✗ | ✗ |
| herdr, only with `--herdr` | release into `~/.local/bin` | ✗ | release into `~/.local/bin` | Homebrew |

On WSL and on Debian or Ubuntu, setup links `fd` to `fdfind` and `bat` to `batcat` when the distro names them so.

On Linux outside WSL, `--no-sudo` makes setup run no sudo command. It skips the package-manager tools and prints the command that installs zsh, tmux, git, curl and wget. It puts lazygit into `~/.local/bin`, installs WezTerm as the nightly AppImage into `~/.local/bin`, and skips the default shell change.

To see where each tool and agent is, run setup with `--only report`. It prints the path of each one.

## Tools that are already on Windows

Setup looks for an existing copy of each tool on the PATH, leaving out its own folder `%LOCALAPPDATA%\Programs\terminal-tools\bin`. It decides by where that copy lives. Windows puts the machine PATH before the user PATH, so a machine-wide copy always runs first.

### Command-line tools and starship

| Setup finds | What setup does |
| --- | --- |
| No copy, or its own copy in `%LOCALAPPDATA%\Programs\terminal-tools\bin` | installs the latest release there. With `--update`, it updates an older copy |
| A copy from winget in your user profile (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`) | asks per tool. `--winget-versions replace` replaces it without asking. `--winget-versions keep` and `--unattended` keep it and print the replace command |
| A machine-wide copy, for example in `C:\Program Files` | keeps it and installs no second copy, because removing it needs administrator rights |
| Any other copy in your user profile, for example from scoop or cargo | keeps it and installs no second copy |
| A winget copy behind the copy that runs first, for example behind a machine-wide copy | asks to uninstall it, because it never runs. `--winget-versions replace` uninstalls it without asking. `keep` and `--unattended` keep it. Setup installs no copy of its own in this case |
| starship in `%LOCALAPPDATA%\Programs\starship`, from an earlier setup version | moves it: installs the new copy, checks it, then removes the old folder and its PATH entry |

A replace runs in this order, so a failed step leaves the winget copy in place:

1. Setup installs its copy into `%LOCALAPPDATA%\Programs\terminal-tools\bin`.
2. It runs `<tool> --version` on its copy. When that fails, it stops and keeps the winget copy.
3. It runs `winget uninstall --id <id> --exact --scope user --silent`. The id comes from the winget package folder, for example `BurntSushi.ripgrep.MSVC`.
4. It removes the user PATH entries that pointed into the removed winget folder. Before that, it saves the old user PATH to `%LOCALAPPDATA%\terminal-setup\user-path-<date>-<time>.txt`.

`--scope user` means that setup can never uninstall a machine-wide winget package.

### WezTerm, runtimes and agents

| Setup finds | WezTerm | Python, Node.js | Claude Code, Copilot CLI, Codex |
| --- | --- | --- | --- |
| No copy | installs its copy | installs its copy | installs its copy, only with `--agents` |
| A machine-wide copy | changes nothing. With `--update`, it prints an info line | prints an info line. When the version is too old, it prints a warning | prints an info line with `--update`, only for an agent named in `--agents` |
| Its own copy in `%LOCALAPPDATA%\Programs\WezTerm` or `nodejs` | `--update` updates it | `--update` updates it | not applicable |
| A copy from winget in your user profile | asks, like the command-line tools above, when that copy is on PATH. When it is not on PATH, setup installs nothing | keeps it. When the version is too old, setup installs its own copy and warns that the old copy can come first on PATH | keeps it. With `--update`, it runs `<agent> update` on that copy, only for an agent named in `--agents` |
| Any other user-profile copy | keeps it. `--update` leaves it as it is | as above | as above |

To find which copy runs, use `Get-Command <tool> -All` in PowerShell. The first line is the copy that runs.

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
| Default shell | WSL, Linux, macOS | Setup runs `chsh` to make zsh the login shell. It needs your password, or root in unattended mode. `--no-sudo` skips it |

## How setup installs

### Common baseline (all supported platforms)

- Core shell tools: `zsh`, `tmux`, `git`, `curl`, `wget`
- Agent-first CLI tools: `lazygit`, `git-lfs`, `direnv`, `just`, `fzf`, `fd`/`fd-find`, `bat`, `ripgrep`, `jq`, `yq`, `shellcheck`, `tree`, `xh`, `ast-grep`, `sd`, `git-delta`, `typos`, `uv`
- Agent image tool: `img-zoom`, installed with `uv tool install`. It crops a pixel box from an image file and magnifies it so an agent can read fine detail. Run from Windows, setup installs it both in WSL and natively on Windows (its folder goes on the user PATH); run inside WSL or on Linux/macOS, it installs it there. uv installs it from a copy setup keeps in `~/.local/share/terminal-setup/img_zoom_tool` (Windows: `%LOCALAPPDATA%\terminal-setup\img_zoom_tool`), so `uv tool upgrade` keeps working after `uv cache clean`. `img-zoom --python` prints its Python, which has Pillow and OpenCV for measuring scripts (Pillow only on Windows on ARM, where OpenCV publishes no build)
- Runtimes: Python 3.14 from `uv python install 3.14 --default`, which puts `python` and `python3` in `~/.local/bin`; `--update` upgrades a uv-managed 3.14 to the latest patch. `node` (latest v26): user-local in `~/.local` on WSL, Linux and macOS, and on Windows from the official zip into `%LOCALAPPDATA%\Programs\nodejs`, checked against `SHASUMS256.txt` and added to the user PATH. npm installs global packages into that folder, so they stay when Node.js is updated. Setup warns when an older Node.js elsewhere may come first on PATH
- Coding agents (only with `--agents`): each agent comes from the method that its vendor puts first. Claude Code from its native installer (`claude.ai/install.sh`, `claude.ai/install.ps1`). OpenAI Codex from its installer (`chatgpt.com/codex/install.sh`, `install.ps1`); with `--unattended`, setup sets `CODEX_NON_INTERACTIVE=1`, so the installer asks nothing and keeps an existing npm copy. GitHub Copilot CLI from its installer `gh.io/copilot-install` in WSL, Linux and macOS, and with `npm install -g @github/copilot` on Windows, because that installer only calls winget on Windows. Run from Windows, setup installs them in WSL and natively on Windows. An agent that is already on PATH is skipped. In WSL, a Windows copy under `/mnt` does not count. Setup never installs or updates an agent that you did not name: `--update` runs `<agent> update` only for the agents in `--agents`
- Config files: `wezterm.lua`, `.tmux.conf`, `.zshrc`, `starship.toml`, micro `settings.json`, `~/.claude/statusline.sh` (Claude Code status line) and `~/.claude/skills/img-zoom/SKILL.md` (tells Claude Code that `img-zoom` exists), both only when the `~/.claude` folder exists and `--skip-claude` is not set. The skill goes to each side where `img-zoom` is installed: the WSL home and, when setup runs from Windows, `%USERPROFILE%\.claude`
- Claude Code skills from [basicly](https://github.com/niksavis/basicly): `~/.claude/skills/cli-tools`, with one reference file for each of 25 tools in `cli-tools/references/`, written by `basicly skills-user` at the basicly version this repository pins. Run from Windows, setup writes it in the WSL home and in `%USERPROFILE%\.claude`. A rerun removes the separate `tool-<name>` skills that older versions of setup wrote, and leaves every skill that you wrote yourself alone. It needs network access to fetch basicly with `uv`, is skipped when `~/.claude` is missing, and `--skip-claude` skips it

`lazygit` and `node` are installed from the latest upstream release archives (not distro/Homebrew package versions) and their downloads are sha256-verified against the published checksum files.

### Platform differences

#### Windows (PowerShell / Git Bash)

- Targets WSL2 Ubuntu as the primary shell environment
- Accepts any Debian-family default distro: its `/etc/os-release` must name `ubuntu` or `debian` in `ID` or `ID_LIKE`, because setup installs system packages with apt. Setup refuses any other distro before it installs anything, and names the distro. Only Ubuntu is tested.
- Windows host installs: WezTerm from its portable release archive into `%LOCALAPPDATA%\Programs\WezTerm`, starship and the command-line tools from their release archives into `%LOCALAPPDATA%\Programs\terminal-tools\bin` (no admin rights or MSI needed; winget copies are kept unless you add `--winget-versions replace`), plus the VS Code Remote - WSL extension
- WSL and native Debian or Ubuntu links: `fd` -> `fdfind`, `bat` -> `batcat`
- Config destinations: Windows `wezterm.lua` under `%USERPROFILE%\.config\wezterm\`, WSL files under `~`

#### Linux / macOS / WSL terminal

- Installs directly on the current host
- WezTerm install path: `apt` repo / `pacman` / `dnf` / Homebrew cask (platform-dependent). Inside WSL, setup installs the nightly AppImage into `~/.local/bin` when WezTerm is missing; on Windows, use the WezTerm that setup installs on the Windows host
- Starship install path: Linux install script or Homebrew on macOS
- Config destinations: all files under `~` on the host

By default the setup installs user-locally. Inside WSL, every managed tool goes into `~/.local` without sudo, so re-running updates everything from one place. The exceptions are the apt system packages, and starship when a system copy exists. On Windows, the tools go into `%LOCALAPPDATA%\Programs\` and `%USERPROFILE%\.local\bin`, and setup keeps a machine-wide copy. Tools published on GitHub (fd, bat, ripgrep, xh, ast-grep, sd, just, delta, typos, fzf, jq, yq, shellcheck, git-lfs, direnv, and starship in WSL) come from the project's latest release binary, checked against the sha256 digest GitHub records for the file; nothing is compiled, so a fresh WSL needs no compiler. A re-run skips a tool that is at the latest release, and names `--update` for one that is older. The latest release is read without the GitHub API, which is used only to download; if the API rate limit is reached, set `GITHUB_TOKEN`. `--system-install` opts into the system-wide package-manager path (apt/brew, needs sudo/admin). On a native Linux host the default stays on apt (a user-local host install is not yet implemented there), except `yq`, which always comes from the mikefarah release so that every Linux host has the same `yq`; macOS uses Homebrew, which needs no admin, except lazygit, which goes into `/usr/local/bin` with sudo unless you add `--no-sudo`. The deprecated `--user-install` flag is a no-op kept for compatibility.

A fresh Ubuntu WSL lacks some system packages that only apt can install: `zsh`, `tmux` and `tree`, `podman` for containers, and `bubblewrap` and `socat`, which the Claude Code sandbox (`/sandbox`) needs on WSL2, and `libatomic1`, which Node.js 26 needs. When any are missing, setup asks once to run `sudo apt-get update && sudo apt-get upgrade -y && sudo apt-get install -y <missing packages>`; when you decline, when the run cannot prompt, or with `--no-sudo`, it prints that command for you to run. It adds `podman-docker`, which provides a `docker` command backed by podman, only when no Docker is installed, because that package would replace `docker.io` or `docker-ce-cli`. `--system-install` runs the command without asking.

After installing, the setup reconciles duplicates: it reports every tool present both in `~/.local/bin` and system-wide, with both versions (for example `lazygit: user-local 0.63.0 vs system 0.60.0`), then asks per tool whether to remove the system copy. `--system-versions uninstall` removes them all without prompting (requires sudo); `--system-versions keep` only reports. Headless runs never prompt or hang; they report and explain instead.

> **Note:** When setup installs WezTerm, starship or the command-line tools on Windows, it uses the portable release archives in `%LOCALAPPDATA%\Programs\` and the user PATH is updated (no admin rights or MSI needed). You must restart your terminal for the new PATH to take effect; until then the setup report marks them OK with a restart hint.

No admin rights are needed on Windows, apart from installing WSL itself: tools install into your user profile. In WSL, the apt system packages and the default shell change need root once. Setup asks, or prints the command. On macOS, tools install through Homebrew, but lazygit goes into `/usr/local/bin` with sudo; add `--no-sudo` to put it into `~/.local/bin`. Add `--system-install` for a system-wide install through apt/brew. On a native Linux host the default installs via apt and uses sudo.

## Platform behaviour

### Windows, with WSL

Run from Windows PowerShell:

```powershell
irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 | iex
```

1. `install.ps1` installs uv into `%USERPROFILE%\.local\bin` when uv is missing.
2. uv downloads Python 3.14 and runs the setup.
3. Setup checks WSL, the default distro, and `git`, `curl` and `wget` in that distro. When one is missing, setup stops.
4. Setup installs the WSL system packages as root: zsh, tmux, tree, podman, bubblewrap, socat, libatomic1, and podman-docker when no Docker is present. In an interactive run, setup asks first. With `--unattended`, it uses `wsl -u root` and asks for no password.
5. Setup installs the command-line tools, uv, Python, Node.js, starship and img-zoom into the WSL home.
6. Setup installs WezTerm, Python, Node.js and img-zoom on the Windows host, in the user profile. It installs starship and the command-line tools into `%LOCALAPPDATA%\Programs\terminal-tools\bin`, and handles winget copies as described in [Tools that are already on Windows](#tools-that-are-already-on-windows).
7. Setup installs the agents that you name with `--agents`, on both sides.
8. Setup writes the config files on both sides, and the VS Code settings.

Setup never runs as administrator. A tool that your organisation installed machine-wide stays as it is. See [Managed Windows machines](user-guide.md#managed-windows-machines).

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
```

A last line follows. It names the command to run again after you install WSL, with the release that ran.

The same stop occurs when the default distro is not Debian or Ubuntu. To continue, set up WSL with [Windows and WSL setup](windows-wsl-setup.md), then run the install again.

The setup has no mode for the Windows host alone. uv stays installed. To remove it, run `uv self uninstall`.

### Inside WSL

Run in the WSL shell:

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh
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

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --only report
```

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --only report
```

The report lists each tool with its path and its version, and each config file. On Windows it lists the Windows host and the WSL distro. It warns about Python older than 3.14 and Node.js older than v26, the versions that setup installs. For each Windows command-line tool it also shows the origin: `terminal-tools`, `winget`, `machine-wide` or `user profile`. It warns about a winget copy that never runs, because another copy comes first on PATH.
