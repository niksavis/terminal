# Windows and WSL setup

The terminal setup needs WSL on Windows. Without WSL, setup stops and installs nothing. This page tells you how to install WSL 2 with Ubuntu, and what each platform needs before you run the install.

WSL means Windows Subsystem for Linux. It runs a Linux distro inside Windows. Setup installs the Linux tools in that distro.

## Prerequisites

### All platforms

- Internet access to the hosts in [Network access](#network-access).
- `git`, `curl` and `wget` in the shell where setup installs the tools. Setup checks them first and stops when one is missing. It does not install them.
- No administrator rights for setup itself. The one exception is the WSL install on Windows, once for each machine.

### Windows

| Need | Why | How to check |
| --- | --- | --- |
| Windows 10 version 2004 (build 19041) or newer, or Windows 11 | `wsl --install` needs it | Run `winver` |
| Virtualization on in the BIOS or UEFI firmware | WSL 2 runs a small virtual machine | See [Enable virtualization on Windows](https://support.microsoft.com/windows/c5578302-6e43-4b4b-a449-8ced115f58e1) |
| Administrator rights, once | `wsl --install` turns on Windows features | Ask IT on a managed machine |
| A Debian or Ubuntu WSL distro as the default distro | Setup installs Linux packages with `apt` | Run `wsl -l -v` |
| `git`, `curl` and `wget` in the distro | Setup needs them and does not install them | See [Step 4](#step-4-check-the-distro) |

Optional on Windows:

- **winget.** Setup needs it only to replace or remove copies that winget installed.
- **PowerShell 7 (`pwsh`).** Setup adds the starship prompt to its profile, and WezTerm offers it in the launch menu.
- **Git for Windows.** Setup adds the starship prompt to Git Bash. The Claude Code status line on the Windows host needs Git Bash.
- **VS Code.** When `code` is on PATH, setup installs the Remote - WSL extension and makes WSL the default VS Code terminal.

Setup does not install these. Install them from your software catalogue or from the vendor.

The Windows version and the virtualization rule come from the Microsoft pages [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install) and [Troubleshooting WSL](https://learn.microsoft.com/en-us/windows/wsl/troubleshooting), read on 2026-10-13.

### Linux

- `apt`, `pacman` or `dnf`. Only Ubuntu is tested.
- `sudo` rights. Setup installs packages with `sudo` by default.
- `git`, `curl` and `wget`.

### macOS

- Homebrew. Install it from <https://brew.sh>.
- `wget`. The macOS base system has no `wget`. Run `brew install wget`.
- `git` and `curl`. Run `git --version` and `curl --version` to check.
- Your login password. Setup installs lazygit into `/usr/local/bin` with `sudo`. Add `--no-sudo` to avoid it.

## Install WSL on Windows

### Step 1: Install WSL and Ubuntu

Open PowerShell as administrator: right-click PowerShell and select **Run as administrator**. Run:

```powershell
wsl --install -d Ubuntu-24.04
```

Restart Windows when the command asks you to.

On a managed machine without administrator rights, ask IT to run this command for you. Or install Ubuntu 24.04 from Software Center or the Microsoft Store, if your organisation offers it.

When WSL is already installed, `wsl --install` prints the help text. Then run `wsl --list --online` to see the distro names, and install one with `wsl --install -d <name>`.

### Step 2: Create your Linux user

Open **Ubuntu 24.04** from the Start menu. The first start unpacks files and takes longer than later starts. Ubuntu asks for a new user name and a password.

Remember the password. Setup asks for it once, to install the Linux system packages with `sudo`. It is not your Windows password.

### Step 3: Check the WSL version and the default distro

In a normal PowerShell window, run:

```powershell
wsl -l -v
```

The output shows a star (`*`) beside the default distro. The `VERSION` column must show `2`.

- When the version is `1`, run `wsl --set-version Ubuntu-24.04 2`.
- When another distro has the star, run `wsl --set-default Ubuntu-24.04`.

Setup always uses the default distro. With a distro that is not Debian or Ubuntu as the default, setup stops before it installs anything.

### Step 4: Check the distro

Open Ubuntu and run:

```bash
command -v git curl wget
```

The output must show three paths. When a path is missing, install the missing tools:

```bash
sudo apt-get update && sudo apt-get install -y git curl wget
```

### Step 5: Run the install

Run the install from a normal PowerShell window, not as administrator:

```powershell
irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 | iex
```

Setup asks once for your Linux password from Step 2. To add coding agents, see [Quick install](../README.md#install).

### Step 6: Restart and check

Close all terminal windows, so that the new PATH takes effect. Then run:

```powershell
& ([scriptblock]::Create((irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1))) --only report
```

Start WezTerm from the Start menu. It opens a zsh shell in Ubuntu.

[What gets installed](what-gets-installed.md) lists each tool that the install adds.

## Problems

| Symptom | Cause | Fix |
| --- | --- | --- |
| `Error: 0x80370102 The virtual machine could not be started because a required feature is not installed.` | Virtualization is off, or the Virtual Machine Platform feature is off | Turn on virtualization in the BIOS or UEFI firmware. Turn on **Virtual Machine Platform** in Windows Features. Restart Windows |
| `wsl --install` hangs at 0.0% | The download from the Store stops | Run `wsl --install --web-download -d Ubuntu-24.04` |
| `wsl --install` fails in a normal PowerShell window | No administrator rights | Ask IT, or install Ubuntu from Software Center |
| Setup prints `wsl: WSL is not installed or not responsive` | WSL is missing | Do Step 1 to Step 3 |
| Setup prints `wsl-distro: ... is not Debian-family` | The default distro is not Debian or Ubuntu | Do Step 1, then `wsl --set-default Ubuntu-24.04` |
| Setup prints `git not found in WSL` | The distro has no `git` | Do Step 4 |
| Setup prints an `apt-get` command | Setup could not run `sudo` | Run that command in Ubuntu, then run the install again |
| `python` opens the Microsoft Store | The Store app alias comes first on PATH | Turn off the `python.exe` and `python3.exe` App execution aliases in Settings > Apps > Advanced app settings |
| A machine-wide tool is too old | Your organisation installed it | Ask IT, or use Software Center. See [Managed Windows machines](user-guide.md#managed-windows-machines) |

The first two rows come from the Microsoft pages above.

## Network access

A corporate firewall or proxy must allow these hosts. The list comes from the setup code and the bootstrap scripts.

| Host | Used for |
| --- | --- |
| `github.com`, `api.github.com`, and the GitHub release download hosts | `install.ps1` and `install.sh`, the setup archive, each tool release, the release digests, the basicly `cli-tools` skill |
| `astral.sh` | The uv installer. uv also downloads Python from GitHub |
| `pypi.org`, `files.pythonhosted.org` | The setup package dependencies and the img-zoom dependencies (Pillow, OpenCV) |
| `nodejs.org` | Node.js archives and their checksums |
| `starship.rs` | The starship installer on Linux, and inside WSL |
| The Ubuntu `apt` mirrors | The WSL system packages |
| `apt.fury.io` | The WezTerm `apt` repository on Linux outside WSL |
| `claude.ai` | The Claude Code installer, only with `--agents` |
| `registry.npmjs.org` | Copilot CLI and Codex, only with `--agents` |
| The VS Code Marketplace | The Remote - WSL extension |

When the GitHub API limit stops a download, set the `GITHUB_TOKEN` environment variable and run the install again.
