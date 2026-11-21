from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404
from collections.abc import Callable
from functools import cache, partial
from pathlib import Path

from . import release_install
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
from .status import Installed, state, version_of

AGENTS = ("claude", "copilot", "codex")
NPM_PACKAGES = {
    "claude": "@anthropic-ai/claude-code",
    "codex": "@openai/codex",
    "copilot": "@github/copilot",
}
SHELL_INSTALL_SCRIPTS = {
    "claude": "curl -fsSL https://claude.ai/install.sh | bash",
    "copilot": "curl -fsSL https://gh.io/copilot-install | bash",
    "codex": "curl -fsSL https://chatgpt.com/codex/install.sh | sh",
}
CLAUDE_INSTALL_PS1 = "irm https://claude.ai/install.ps1 | iex"
CODEX_INSTALL_PS1 = "irm https://chatgpt.com/codex/install.ps1 | iex"
CODEX_NON_INTERACTIVE = "CODEX_NON_INTERACTIVE=1"
CODEX_DAEMON_ONLY = "CODEX_INSTALL_DAEMON_ONLY=1"
LATEST_VERSION_URLS = {
    "claude": "https://downloads.claude.ai/claude-code-releases",
    "codex": "https://releases.openai.com/codex/channels/latest",
    "copilot": "https://github.com/github/copilot-cli/releases/latest",
}
AGENTS_COMMAND_TEMPLATES = {
    "agents": "agents.sh",
    "agents.ps1": "agents.ps1",
    "agents.cmd": "agents.cmd",
}
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
_PLACEHOLDER = re.compile(r"__[A-Z0-9_]+__")
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


@cache
def latest_agent_version(agent: str) -> str:
    try:
        if agent == "copilot":
            text = release_install.latest_tag("github/copilot-cli")
        elif agent == "codex":
            text = str(
                json.loads(release_install.fetch(LATEST_VERSION_URLS["codex"])).get("tag_name", "")
            )
        else:
            text = release_install.fetch(f"{LATEST_VERSION_URLS['claude']}/latest").decode()
    except OSError, ValueError, AttributeError, release_install.InstallError:
        return ""
    return version_of(text)


def _reports_current(
    runner: Runner, agent: str, where: str, read_version: Callable[[], str]
) -> bool:
    latest = latest_agent_version(agent)
    if not latest:
        return False
    printed = read_version()
    if not version_of(printed) or state(Installed(agent, agent, printed), latest) != "ok":
        return False
    runner.reporter.success(f"{agent} {version_of(printed)} is up to date {where}")
    return True


def _shell_version(runner: Runner, agent: str, wsl_distro: str | None) -> str:
    return str(_run_shell_read(runner, version_query(agent), wsl_distro=wsl_distro).stdout or "")


def _windows_version(runner: Runner, found: str) -> str:
    return str(runner.run([found, "--version"], check=False, dry_run_safe=True).stdout or "")


def version_query(agent: str) -> str:
    return f"{_LOCAL_PATH}{agent} --version 2>/dev/null | head -n 1"


def shell_update_script(agent: str) -> str:
    return f"{_LOCAL_PATH}{agent} update"


def _ensure_shell_agent(
    runner: Runner, agent: str, *, update: bool, wsl_distro: str | None, install: bool = True
) -> None:
    where = "in WSL" if wsl_distro else "on this host"
    present = _run_shell_read(runner, present_query(agent), wsl_distro=wsl_distro).returncode == 0
    if not present and not install:
        return
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
    if _reports_current(runner, agent, where, lambda: _shell_version(runner, agent, wsl_distro)):
        return
    _run_shell_command(
        runner, shell_update_script(agent), label=f"update {agent} {where}", wsl_distro=wsl_distro
    )


def windows_agent_path(runner: Runner, platform: PlatformInfo, agent: str) -> str | None:
    found = runner.which(agent)
    if found is not None:
        return found
    for local in (
        platform.home / ".local" / "bin" / f"{agent}.exe",
        platform.user_programs_dir / "OpenAI" / "Codex" / "bin" / f"{agent}.exe",
    ):
        if local.exists():
            return str(local)
    return None


def _windows_npm(runner: Runner) -> str:
    npm = runner.which("npm")
    if npm is None:
        raise RuntimeError(
            "npm is not on the Windows PATH; the Node.js step must succeed first. "
            f"Then run: {rerun_command()}"
        )
    return npm


def _install_windows_agent(runner: Runner, platform: PlatformInfo, agent: str) -> None:
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


def _ensure_windows_agent(
    runner: Runner, platform: PlatformInfo, agent: str, *, update: bool, install: bool = True
) -> None:
    found = windows_agent_path(runner, platform, agent)
    if found is None and not install:
        return
    if found is None:
        _install_windows_agent(runner, platform, agent)
        return
    if not update:
        runner.reporter.success(f"{agent} is present on Windows ({found})")
        return
    if not is_user_scope(found, platform):
        report_machine_scope(runner, agent, "", found, minimum=None)
        return
    if _reports_current(runner, agent, "on Windows", lambda: _windows_version(runner, found)):
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
        named = agent in selected
        if not named and not update:
            continue
        verb = "install" if named and not update else "update"
        attempt(
            runner,
            f"{verb} {agent}",
            partial(
                _ensure_shell_agent,
                runner,
                agent,
                update=update,
                wsl_distro=wsl_distro,
                install=named,
            ),
        )
        if windows_host:
            attempt(
                runner,
                f"{verb} {agent} on Windows",
                partial(
                    _ensure_windows_agent, runner, platform, agent, update=update, install=named
                ),
            )


def installed_agents(runner: Runner, platform: PlatformInfo) -> tuple[str, ...]:
    windows_host = platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()
    wsl_distro = _wsl_distro(platform) if windows_host else None
    found = []
    for agent in AGENTS:
        shell = _run_shell_read(runner, present_query(agent), wsl_distro=wsl_distro).returncode == 0
        if shell or (windows_host and windows_agent_path(runner, platform, agent) is not None):
            found.append(agent)
    return tuple(found)


def codex_daemon_install_script() -> str:
    return SHELL_INSTALL_SCRIPTS["codex"].replace(
        "| sh", f"| {CODEX_DAEMON_ONLY} {CODEX_NON_INTERACTIVE} sh"
    )


def _agents_command_values() -> dict[str, str]:
    return {
        "__CLAUDE_INSTALL__": SHELL_INSTALL_SCRIPTS["claude"],
        "__CODEX_INSTALL__": shell_install_script("codex", unattended=True),
        "__COPILOT_INSTALL__": SHELL_INSTALL_SCRIPTS["copilot"],
        "__CODEX_DAEMON_INSTALL__": codex_daemon_install_script(),
        "__CLAUDE_INSTALL_PS1__": CLAUDE_INSTALL_PS1,
        "__CODEX_INSTALL_PS1__": CODEX_INSTALL_PS1,
        "__CLAUDE_LATEST_URL__": LATEST_VERSION_URLS["claude"],
        "__CODEX_LATEST_URL__": LATEST_VERSION_URLS["codex"],
        "__COPILOT_LATEST_URL__": LATEST_VERSION_URLS["copilot"],
        "__NPM_CLAUDE__": NPM_PACKAGES["claude"],
        "__NPM_CODEX__": NPM_PACKAGES["codex"],
        "__NPM_COPILOT__": NPM_PACKAGES["copilot"],
    }


def render_template(file_name: str, values: dict[str, str]) -> str:
    text = (_TEMPLATE_DIR / file_name).read_text(encoding="utf-8")
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    leftover = _PLACEHOLDER.search(text)
    if leftover is not None:
        raise RuntimeError(f"{file_name} keeps {leftover.group()}")
    if file_name.endswith(".cmd"):
        text = text.replace("\n", "\r\n")
    return text


def render_agents_command(name: str) -> str:
    return render_template(AGENTS_COMMAND_TEMPLATES[name], _agents_command_values())


_WSL_COMMAND_INSTALL = (
    'src=$(wslpath -u "$1") && mkdir -p "$HOME/.local/bin" && '
    'cp -f "$src" "$HOME/.local/bin/$2" && chmod 755 "$HOME/.local/bin/$2"'
)


def install_wsl_command(runner: Runner, platform: PlatformInfo, name: str, content: str) -> None:
    staged = platform.home / ".local" / "share" / "terminal" / name
    runner.write_text(staged, content)
    runner.run(
        wsl_exec_command(
            _wsl_distro(platform), ["sh", "-c", _WSL_COMMAND_INSTALL, "sh", str(staged), name]
        ),
        label=f"install the {name} command in WSL",
    )


def write_executable(runner: Runner, path: Path, content: str) -> None:
    runner.write_text(path, content)
    if not runner.dry_run:
        path.chmod(0o755)


def deploy_agents_command(runner: Runner, platform: PlatformInfo) -> None:
    if platform.os == OperatingSystem.MACOS:
        runner.reporter.info("The agents command needs bash 4, so setup skips it on macOS.")
        return
    bin_dir = platform.home / ".local" / "bin"
    if platform.os != OperatingSystem.WINDOWS or is_running_in_wsl():
        write_executable(runner, bin_dir / "agents", render_agents_command("agents"))
        return
    for name in ("agents.ps1", "agents.cmd"):
        runner.write_text(bin_dir / name, render_agents_command(name))
    _add_to_user_path(runner, bin_dir)
    install_wsl_command(runner, platform, "agents", render_agents_command("agents"))


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


_DAEMON_SHELL = (
    'PATH="$HOME/.local/bin:$PATH"; command -v codex >/dev/null 2>&1 || exit 0; '
    "codex --version 2>/dev/null | head -n 1; "
    'readlink "${CODEX_HOME:-$HOME/.codex}/packages/app-server-daemon/current" 2>/dev/null '
    "| sed 's#.*/##'"
)
_DAEMON_WINDOWS = (
    "$c = Get-Command codex -ErrorAction SilentlyContinue; if (-not $c) { exit 0 }; "
    "& $c.Source --version | Select-Object -First 1; "
    "$d = Get-Item (Join-Path $env:USERPROFILE '.codex\\packages\\app-server-daemon\\current') "
    '-ErrorAction SilentlyContinue; if ($d) { Split-Path -Leaf "$($d.Target)" }'
)


def _daemon_lag(output: str) -> tuple[str, str] | None:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    codex, daemon = version_of(lines[0]), version_of(lines[1])
    if not codex or not daemon:
        return None
    numbers = [tuple(int(part) for part in value.split(".")) for value in (codex, daemon)]
    return (codex, daemon) if numbers[1] < numbers[0] else None


def report_daemon_lag(runner: Runner, platform: PlatformInfo) -> None:
    windows_host = platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()
    sides = [
        (
            "in WSL" if windows_host else "",
            _run_shell_read(
                runner, _DAEMON_SHELL, wsl_distro=_wsl_distro(platform) if windows_host else None
            ).stdout
            or "",
        )
    ]
    if windows_host:
        result = runner.run(
            ["powershell", "-NoProfile", "-Command", _DAEMON_WINDOWS],
            check=False,
            dry_run_safe=True,
        )
        sides.append(("on Windows", result.stdout or ""))
    for where, output in sides:
        lag = _daemon_lag(str(output))
        if lag is None:
            continue
        codex, daemon = lag
        place = f" {where}" if where else ""
        runner.reporter.info(
            f"The Codex app-server daemon{place} is {daemon}, older than codex {codex}. "
            "Setup does not update it, because that stops running Codex work. "
            "To update it, run: agents update"
        )
