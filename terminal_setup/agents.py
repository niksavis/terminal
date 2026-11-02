from __future__ import annotations

import argparse
import subprocess  # nosec B404
from functools import partial

from .platform import (
    OperatingSystem,
    PlatformInfo,
    is_running_in_wsl,
    rerun_command,
    wsl_exec_command,
)
from .prerequisites import (
    _add_to_user_path,
    _run_shell_command,
    _run_shell_read,
    _wsl_distro,
    attempt,
    is_user_scope,
    report_machine_scope,
)
from .runner import Runner

AGENTS = ("claude", "copilot", "codex")
NPM_PACKAGES = {"copilot": "@github/copilot"}
SHELL_INSTALL_SCRIPTS = {
    "claude": "curl -fsSL https://claude.ai/install.sh | bash",
    "copilot": "curl -fsSL https://gh.io/copilot-install | bash",
    "codex": "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
}
CLAUDE_INSTALL_PS1 = "irm https://claude.ai/install.ps1 | iex"
CODEX_INSTALL_PS1 = "irm https://chatgpt.com/codex/install.ps1 | iex"
CODEX_NON_INTERACTIVE = "CODEX_NON_INTERACTIVE=1"
_LOCAL_PATH = 'PATH="$HOME/.local/bin:$PATH"; '
_HERDR_RUN = 'PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"; exec herdr "$@"'
_HERDR_INTEGRATION_INSTALL = (
    'mkdir -p "$HOME/.$1" && PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH" '
    'exec herdr integration install "$1"'
)


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


def shell_install_script(agent: str, *, unattended: bool = False) -> str:
    script = SHELL_INSTALL_SCRIPTS[agent]
    if agent == "codex" and unattended:
        return script.replace("| sh", f"| {CODEX_NON_INTERACTIVE} sh")
    return script


def windows_codex_command(*, unattended: bool) -> list[str]:
    script = ("$env:CODEX_NON_INTERACTIVE = '1'; " if unattended else "") + CODEX_INSTALL_PS1
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]


def shell_update_script(agent: str) -> str:
    return f"{_LOCAL_PATH}{agent} update"


def _ensure_shell_agent(
    runner: Runner, agent: str, *, update: bool, wsl_distro: str | None
) -> None:
    where = "in WSL" if wsl_distro else "on this host"
    present = _run_shell_read(runner, present_query(agent), wsl_distro=wsl_distro).returncode == 0
    if not present:
        _run_shell_command(
            runner,
            shell_install_script(agent, unattended=runner.unattended),
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
            f"Then run: {rerun_command()}"
        )
    return npm


def _ensure_windows_agent(
    runner: Runner, platform: PlatformInfo, agent: str, *, update: bool
) -> None:
    found = _windows_agent_path(runner, platform, agent)
    if found is None:
        if agent == "claude":
            runner.run(
                ["powershell", "-NoProfile", "-Command", CLAUDE_INSTALL_PS1],
                interactive=True,
                label="install claude on Windows",
            )
            _add_to_user_path(runner, platform.home / ".local" / "bin")
            return
        if agent == "codex":
            runner.run(
                windows_codex_command(unattended=runner.unattended),
                interactive=True,
                label="install codex on Windows",
            )
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
    if not is_user_scope(found, platform):
        report_machine_scope(runner, agent, "", found, minimum=None)
        return
    try:
        runner.run([found, "update"], interactive=True, label=f"update {agent} on Windows")
    except subprocess.CalledProcessError:
        runner.reporter.step(
            f"To retry, run '{agent} update' in Windows PowerShell (powershell.exe)."
        )
        raise


def ensure_agents(
    runner: Runner, platform: PlatformInfo, selected: tuple[str, ...], *, update: bool
) -> None:
    windows_host = platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()
    wsl_distro = _wsl_distro(platform) if windows_host else None
    for agent in AGENTS:
        if agent not in selected:
            continue
        verb = "update" if update else "install"
        attempt(
            runner,
            f"{verb} {agent}",
            partial(
                _ensure_shell_agent,
                runner,
                agent,
                update=update,
                wsl_distro=wsl_distro,
            ),
        )
        if windows_host:
            attempt(
                runner,
                f"{verb} {agent} on Windows",
                partial(_ensure_windows_agent, runner, platform, agent, update=update),
            )


def _herdr_command(platform: PlatformInfo, *arguments: str, script: str = _HERDR_RUN) -> list[str]:
    command = ["sh", "-c", script, "herdr", *arguments]
    if platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl():
        command = wsl_exec_command(_wsl_distro(platform), command)
    return command


def ensure_herdr_integrations(
    runner: Runner, platform: PlatformInfo, selected: tuple[str, ...]
) -> None:
    for agent in AGENTS:
        if agent not in selected:
            continue
        label = f"install the herdr integration for {agent}"
        attempt(
            runner,
            label,
            partial(
                runner.run,
                _herdr_command(platform, agent, script=_HERDR_INTEGRATION_INSTALL),
                label=label,
            ),
        )


def herdr_integration_states(runner: Runner, platform: PlatformInfo) -> dict[str, str]:
    result = runner.run(
        _herdr_command(platform, "integration", "status"), check=False, dry_run_safe=True
    )
    states: dict[str, str] = {}
    for line in result.stdout.splitlines():
        agent, separator, rest = line.partition(": ")
        if separator and agent in AGENTS:
            states[agent] = rest.split(" (/", 1)[0].strip()
    return states
