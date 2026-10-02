from __future__ import annotations

import argparse
from functools import partial

from .platform import OperatingSystem, PlatformInfo, is_running_in_wsl
from .prerequisites import (
    _add_to_user_path,
    _run_shell_command,
    _run_shell_read,
    _wsl_distro,
    attempt,
)
from .runner import Runner

AGENTS = ("claude", "copilot", "codex")
NPM_PACKAGES = {"copilot": "@github/copilot", "codex": "@openai/codex"}
CLAUDE_INSTALL_SH = "curl -fsSL https://claude.ai/install.sh | bash"
CLAUDE_INSTALL_PS1 = "irm https://claude.ai/install.ps1 | iex"
_LOCAL_PATH = 'PATH="$HOME/.local/bin:$PATH"; '


def parse_agents(value: str) -> tuple[str, ...]:
    names = [name.strip().lower() for name in value.split(",") if name.strip()]
    if names == ["all"]:
        return AGENTS
    unknown = [name for name in names if name not in AGENTS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(
            f"unknown agent {', '.join(unknown) or repr(value)}; choose from "
            f"{', '.join(AGENTS)} or all, for example --agents claude,codex"
        )
    return tuple(dict.fromkeys(names))


def present_query(agent: str) -> str:
    return (
        f"{_LOCAL_PATH}found=$(command -v {agent}) || exit 1; "
        'case "$found" in /mnt/*) exit 1;; esac'
    )


def shell_install_script(agent: str) -> str:
    if agent == "claude":
        return CLAUDE_INSTALL_SH
    return f"{_LOCAL_PATH}npm install -g {NPM_PACKAGES[agent]}"


def shell_update_script(agent: str) -> str:
    return f"{_LOCAL_PATH}{agent} update"


def _ensure_shell_agent(
    runner: Runner, agent: str, *, install: bool, update: bool, wsl_distro: str | None
) -> None:
    where = "in WSL" if wsl_distro else "on this host"
    present = _run_shell_read(runner, present_query(agent), wsl_distro=wsl_distro).returncode == 0
    if not present:
        if install:
            _run_shell_command(
                runner,
                shell_install_script(agent),
                label=f"install {agent} {where}",
                wsl_distro=wsl_distro,
            )
        return
    if not update:
        runner.reporter.success(f"{agent} is present {where}")
        return
    _run_shell_command(
        runner, shell_update_script(agent), label=f"update {agent} {where}", wsl_distro=wsl_distro
    )


def _windows_agent_path(runner: Runner, platform: PlatformInfo, agent: str) -> str | None:
    found = runner.which(agent)
    if found is not None:
        return found
    local = platform.home / ".local" / "bin" / f"{agent}.exe"
    return str(local) if local.exists() else None


def _windows_npm(runner: Runner) -> str:
    npm = runner.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm is not on the Windows PATH; the Node.js step must succeed first. "
            "Re-run this setup."
        )
    return npm


def _ensure_windows_agent(
    runner: Runner, platform: PlatformInfo, agent: str, *, install: bool, update: bool
) -> None:
    found = _windows_agent_path(runner, platform, agent)
    if found is None:
        if not install:
            return
        if agent == "claude":
            runner.run(
                ["powershell", "-NoProfile", "-Command", CLAUDE_INSTALL_PS1],
                interactive=True,
                label="install claude on Windows",
            )
            _add_to_user_path(runner, platform.home / ".local" / "bin")
            return
        runner.run(
            [_windows_npm(runner), "install", "-g", NPM_PACKAGES[agent]],
            interactive=True,
            label=f"install {agent} on Windows",
        )
        return
    if not update:
        runner.reporter.success(f"{agent} is present on Windows ({found})")
        return
    runner.run([found, "update"], interactive=True, label=f"update {agent} on Windows")


def ensure_agents(
    runner: Runner, platform: PlatformInfo, selected: tuple[str, ...], *, update: bool
) -> None:
    windows_host = platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()
    wsl_distro = _wsl_distro(platform) if windows_host else None
    for agent in AGENTS:
        install = agent in selected
        attempt(
            runner,
            f"install {agent}",
            partial(
                _ensure_shell_agent,
                runner,
                agent,
                install=install,
                update=update,
                wsl_distro=wsl_distro,
            ),
        )
        if windows_host:
            attempt(
                runner,
                f"install {agent} on Windows",
                partial(
                    _ensure_windows_agent, runner, platform, agent, install=install, update=update
                ),
            )
