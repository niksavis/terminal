from __future__ import annotations

import os
import re
from pathlib import Path

from . import __version__
from .agents import install_wsl_command, render_template, write_executable
from .platform import (
    SETUP_ARCHIVES,
    OperatingSystem,
    PlatformInfo,
    is_running_in_wsl,
    rerun_command,
)
from .prerequisites import _add_to_user_path, _run_shell_read, _wsl_distro
from .runner import Runner

TERMINAL_COMMAND_TEMPLATES = {
    "terminal": "terminal.sh",
    "terminal.ps1": "terminal.ps1",
    "terminal.cmd": "terminal.cmd",
}
_WSL_OTHER = 3
_WSL_REFUSE = (
    "found=$(command -v terminal 2>/dev/null || true); "
    'case "$found" in ""|"$HOME/.local/bin/terminal"|/mnt/*) exit 0;; esac; '
    'echo "$found"; exit 3'
)


_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")


def setup_ref() -> str:
    ref = os.environ.get("TERMINAL_SETUP_REF", "").strip()
    if _REF.fullmatch(ref) and ".." not in ref:
        return ref
    return f"v{__version__}"


def setup_source() -> str:
    return f"{SETUP_ARCHIVES}{setup_ref()}.zip"


RELEASES = "https://github.com/niksavis/terminal/releases"


def render_terminal_command(name: str) -> str:
    values = {
        "__SETUP_SOURCE__": setup_source(),
        "__SETUP_REF__": setup_ref(),
        "__RELEASES__": RELEASES,
    }
    return render_template(TERMINAL_COMMAND_TEMPLATES[name], values)


def _refuse_other(found: str, ours: tuple[Path, ...]) -> None:
    if not found or found.startswith("/mnt/"):
        return
    if any(Path(found) == path for path in ours):
        return
    raise RuntimeError(
        f"another terminal command is on PATH at {found}, so setup does not install its "
        f"terminal command. Rename or remove {found}, then run: {rerun_command()}"
    )


def deploy_terminal_command(runner: Runner, platform: PlatformInfo) -> None:
    bin_dir = platform.home / ".local" / "bin"
    windows_host = platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()
    if not windows_host:
        _refuse_other(runner.which("terminal") or "", (bin_dir / "terminal",))
        write_executable(runner, bin_dir / "terminal", render_terminal_command("terminal"))
        return
    _refuse_other(
        runner.which("terminal") or "",
        (bin_dir / "terminal.cmd", bin_dir / "terminal.ps1"),
    )
    for name in ("terminal.ps1", "terminal.cmd"):
        runner.write_text(bin_dir / name, render_terminal_command(name))
    _add_to_user_path(runner, bin_dir)
    probe = _run_shell_read(runner, _WSL_REFUSE, wsl_distro=_wsl_distro(platform))
    if probe.returncode == _WSL_OTHER:
        _refuse_other(str(probe.stdout).strip() or "terminal in WSL", ())
    install_wsl_command(runner, platform, "terminal", render_terminal_command("terminal"))
