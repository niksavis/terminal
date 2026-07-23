# WSL command reference

## Managing distributions

Run from Windows (PowerShell or cmd), or via `wsl.exe` from inside a distro.

| Task | Command |
| --- | --- |
| List installed distros | `wsl --list --verbose` (`wsl -l -v`) |
| List distros available to install | `wsl --list --online` |
| Install a distro | `wsl --install -d <Distro>` |
| Set the default distro | `wsl --set-default <Distro>` |
| Set a distro to WSL 2 | `wsl --set-version <Distro> 2` |
| Shut down every distro | `wsl --shutdown` |
| Terminate one distro | `wsl --terminate <Distro>` |
| Update the WSL kernel | `wsl --update` |
| Show status and version | `wsl --status`, `wsl --version` |

## Interop and paths

| Task | Command |
| --- | --- |
| See which binary resolves | `command -v <tool>` |
| Open the current dir in Explorer | `explorer.exe .` |
| Windows path to WSL path | `wslpath 'C:\Users\me\file'` |
| WSL path to Windows path | `wslpath -w /home/me/file` |
| Run a Windows executable | `notepad.exe`, `pwsh.exe -c '...'` |

## Configuration

- Per-distro settings live in `/etc/wsl.conf` inside the distro (interop toggles,
  automount options, default user).
- Global VM settings live in `%UserProfile%\.wslconfig` on Windows (memory, CPU,
  and swap caps for the WSL 2 VM).
- Apply `wsl.conf` or `.wslconfig` changes with `wsl --shutdown`, then restart the
  distro.
