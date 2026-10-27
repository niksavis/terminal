# terminal

One command sets up the same terminal for coding agents on Windows, WSL, Linux and macOS: WezTerm, zsh, tmux, starship, the command-line tools that agents use, Python 3.14 and Node.js 26. It needs no admin rights, and you can run it again at any time.

> **Windows needs WSL.** On Windows, setup installs the Linux tools into WSL 2 with an Ubuntu or Debian distro. Without WSL, setup stops and installs nothing. Installing WSL needs administrator rights once: follow [Windows and WSL setup](docs/windows-wsl-setup.md) first.

## Install

Windows (PowerShell or pwsh):

```powershell
irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 | iex
```

WSL, Linux or macOS:

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh
```

These commands install the latest release. Run from Windows, setup sets up the Windows host and the default WSL distro together. Run inside WSL, it sets up only that distro. For cmd and Git Bash, see [Start commands](docs/what-gets-installed.md#start-commands).

To add options, for example no questions and all coding agents (Claude Code, Copilot CLI, Codex):

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --unattended --agents all
```

```bash
curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh -s -- --unattended --agents all
```

Use the same form with `--update` to update every tool, and with `--only report` to see what is installed. All options are in the [User guide](docs/user-guide.md#cli-options).

## What you get

| Tool | What it is for | Windows host | WSL | Linux, macOS |
| --- | --- | --- | --- | --- |
| WezTerm | Terminal with tabs, panes and a launch menu | ✓ | (1) | ✓ |
| zsh | Shell | ✗ | ✓ | ✓ |
| tmux | Sessions that stay alive after the window closes | ✗ | ✓ | ✓ |
| starship | Prompt with the git branch and state | ✓ | ✓ | ✓ |
| ripgrep (`rg`), fd | Fast search in file contents and file names | ✓ | ✓ | ✓ |
| bat, fzf | Read files with line numbers, find files and commands | ✓ | ✓ | ✓ |
| tree | See a folder as a tree | ✗ | ✓ | ✓ |
| ast-grep, sd | Search and replace code safely | ✓ | ✓ | ✓ |
| jq, yq, xh | JSON, YAML and HTTP from the command line | ✓ | ✓ | ✓ |
| typos, shellcheck | Find spelling mistakes and shell script bugs | ✓ | ✓ | ✓ |
| lazygit, delta | Review diffs and stage changes | ✓ | ✓ | ✓ |
| just | Project commands | ✓ | ✓ | ✓ |
| git-lfs, direnv | Large files in git, per-folder environment | ✗ | ✓ | ✓ |
| uv, Python 3.14 | Python and Python tools | ✓ | ✓ | ✓ |
| Node.js 26 | JavaScript runtime and npm | ✓ | ✓ | ✓ |
| img-zoom | Lets an agent read small text in an image | ✓ | ✓ | ✓ |
| podman, bubblewrap, socat | Containers, and the Claude Code sandbox | ✗ | ✓ | ✗ |
| Claude Code, Copilot CLI, Codex | Coding agents, only with `--agents` | ✓ | ✓ | ✓ |

1. Run from Windows, setup does not install WezTerm in WSL: the WezTerm on Windows opens WSL. Run inside WSL, setup installs WezTerm there when it is missing.

Where setup puts the tools:

| Platform | Folder |
| --- | --- |
| Windows host | command-line tools and starship: `%LOCALAPPDATA%\Programs\terminal-tools\bin`. WezTerm: `%LOCALAPPDATA%\Programs\WezTerm`, with a WezTerm entry in the Start menu. Node.js: `%LOCALAPPDATA%\Programs\nodejs`. uv, Python and Claude Code: `%USERPROFILE%\.local\bin`. Codex: `%LOCALAPPDATA%\Programs\OpenAI\Codex\bin`. Copilot CLI: the Node.js folder |
| WSL | `~/.local/bin`, also for the coding agents. zsh, tmux, tree and the container packages come from apt |
| Linux | the package manager. uv, Python, yq and the tools that the package manager does not have: `~/.local/bin`. Node.js: `~/.local`. lazygit: `/usr/local/bin` |
| macOS | Homebrew. uv and Python: `~/.local/bin`. Node.js: `~/.local`. lazygit: `/usr/local/bin` |

On Windows, setup adds each of these folders to your user PATH. It installs no second WezTerm when one is already on PATH or in `C:\Program Files`. At the end, setup prints where WezTerm is installed. A copy that winget installed stays as it is. To replace it with the setup copy, add `--winget-versions replace`. Setup never changes a copy that needs administrator rights.

`git`, `curl` and `wget` must be present before you run setup. Setup also writes the config files for these tools. When the `~/.claude` folder exists, it adds a status line and two skills for Claude Code.

To see the path of each installed tool, run setup with `--only report`.

[What gets installed](docs/what-gets-installed.md) gives each tool's version, its source on each platform, and how a coding agent benefits from it.

## Documentation

| Document | For |
| --- | --- |
| [What gets installed](docs/what-gets-installed.md) | Every tool and config file, versions, sources, and what each shell sets up |
| [Windows and WSL setup](docs/windows-wsl-setup.md) | Prerequisites, and how to install WSL and Ubuntu |
| [User guide](docs/user-guide.md) | Update and check, all options, shortcuts, the prompt, the Claude status line, troubleshooting |
| [Cheat sheet](https://niksavis.github.io/terminal/) | Linux commands, and shell, tmux and WezTerm shortcuts on one page |
| [Contributing](docs/contributing.md) | Change this repository: setup, tests, layout |
| [Releases](docs/releases.md) | Cut a release, and test unreleased `main` |

## License

Released under the [MIT License](LICENSE).
