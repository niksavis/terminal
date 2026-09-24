# WSL command reference

## Manage distributions

Run these from Windows (PowerShell or cmd), or through `wsl.exe` inside a distribution.

| Task | Command |
| --- | --- |
| List installed distributions | `wsl --list --verbose` (`wsl -l -v`) |
| List distributions you can install | `wsl --list --online` |
| Install a distribution | `wsl --install -d <Distro>` |
| Set the default distribution | `wsl --set-default <Distro>` |
| Set a distribution to WSL 2 | `wsl --set-version <Distro> 2` |
| Stop every distribution | `wsl --shutdown` |
| Stop one distribution | `wsl --terminate <Distro>` |
| Update the WSL kernel | `wsl --update` |
| Show status and version | `wsl --status`, `wsl --version` |

## Interop and paths

| Task | Command |
| --- | --- |
| Show which binary resolves | `command -v <tool>` |
| Open the current directory in Explorer | `explorer.exe .` |
| Change a Windows path to a WSL path | `wslpath 'C:\Users\me\file'` |
| Change a WSL path to a Windows path | `wslpath -w /home/me/file` |
| Run a Windows program | `notepad.exe`, `pwsh.exe -c '...'` |

## Configuration

| File | Location | Holds |
| --- | --- | --- |
| `wsl.conf` | `/etc/wsl.conf` in the distribution | interop, automount options, default user |
| `.wslconfig` | `%UserProfile%\.wslconfig` on Windows | memory, CPU and swap limits of the WSL 2 VM |

Run `wsl --shutdown` and start the distribution again to apply a change to either file.
