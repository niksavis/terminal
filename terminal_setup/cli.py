from __future__ import annotations

import argparse
import os
import shlex
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from . import (
    agents,
    configs,
    platform,
    prerequisites,
    release_install,
    terminal_command,
    windows_tools,
)
from . import status as tool_status
from .platform import is_running_in_wsl, rerun_command, setup_command, wsl_exec_command
from .runner import ConsoleReporter, Runner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="terminal-setup",
        description="Install and configure a cross-platform terminal environment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  terminal-setup                 user-local install and configuration (no admin)\n"
            "  terminal-setup --system-install install system-wide via the package manager\n"
            "  terminal-setup --dry-run       preview the steps without making changes\n"
            "  terminal-setup --only check    verify prerequisites, then exit\n"
            "  terminal-setup --only config   re-apply configuration only (no package installs)\n"
            "  terminal-setup --only report   print the verification report, then exit\n"
            "  terminal-setup --report        full run, then print the verification report\n"
            "  terminal-setup --unattended    full run that never prompts (scripts, agents)\n"
            "  terminal-setup --agents all    also install Claude Code, Copilot CLI and Codex\n"
            "  terminal-setup --skip-claude   install everything except the Claude status line\n"
            "  terminal-setup --no-nerd-font  use the universal (no Nerd Font) status line\n"
        ),
    )

    run = parser.add_argument_group("run options")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the steps that would be executed without making changes.",
    )
    run.add_argument(
        "--only",
        choices=("check", "config", "report", "status"),
        help=(
            "Limit the run to one phase and exit: 'check' verifies prerequisites, "
            "'config' re-applies configuration without installing packages, "
            "'report' prints the verification report."
        ),
    )
    run.add_argument(
        "--unattended",
        action="store_true",
        help=(
            "Never prompt: answer 'no' to every question, keep system versions, and install "
            "missing WSL system packages as root through 'wsl -u root' or passwordless sudo, "
            "or print the command when neither works. The whole distro is upgraded only "
            "with --update."
        ),
    )
    run.add_argument(
        "--report",
        action="store_true",
        help="After a full run, print a verification report for tools and deployed configs.",
    )

    skip = parser.add_argument_group("skip components")
    skip.add_argument(
        "--skip-vscode",
        action="store_true",
        help="Skip VS Code settings and extension configuration.",
    )
    skip.add_argument(
        "--skip-starship",
        action="store_true",
        help="Skip starship prompt installation and configuration.",
    )
    skip.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip the Claude Code status line (installed by default when ~/.claude exists).",
    )

    status_line = parser.add_argument_group("status line")
    status_line.add_argument(
        "--no-nerd-font",
        action="store_true",
        dest="no_nerd_font",
        help="Install the universal (no Nerd Font) build of the Claude Code status line.",
    )

    install = parser.add_argument_group("install behavior")
    install.add_argument(
        "--system-install",
        action="store_true",
        dest="system_install",
        help=(
            "Install tools system-wide with the OS package manager (apt/brew), using "
            "sudo/admin. Default is a user-local install into ~/.local without admin rights."
        ),
    )
    install.add_argument(
        "--user-install",
        action="store_true",
        help=(
            "Deprecated: a user-local install without admin rights is now the default, "
            "so this flag is a no-op kept for backwards compatibility."
        ),
    )
    install.add_argument(
        "--no-sudo",
        action="store_true",
        dest="no_sudo",
        help=(
            "Never use sudo: force the user-local install path everywhere (the default on "
            "Windows and WSL), and print the apt command for missing WSL system packages "
            "instead of offering to run it."
        ),
    )
    install.add_argument(
        "--update",
        action="store_true",
        help=(
            "Install the latest release of each user-local tool, Python and Node that is out of "
            "date; without it, setup only reports which ones are."
        ),
    )
    install.add_argument(
        "--agents",
        type=agents.parse_agents,
        default=(),
        metavar="NAMES",
        help=(
            "Install these coding agents when they are absent: a comma list of claude, "
            "copilot and codex, or all. With --update, setup updates only these agents."
        ),
    )
    install.add_argument(
        "--herdr",
        action="store_true",
        help=(
            "Install herdr, the runtime that keeps coding agents running, in WSL, on Linux "
            "and on macOS. With --update, setup updates herdr only with this option."
        ),
    )
    install.add_argument(
        "--winget-versions",
        choices=("keep", "replace"),
        dest="winget_versions",
        help=(
            "Windows only: how to handle a tool that winget installed in your user profile. "
            "'replace' installs the setup copy, uninstalls the winget copy and removes its PATH "
            "entry; 'keep' leaves it. Prompts per tool when unset; --unattended keeps."
        ),
    )
    install.add_argument(
        "--system-versions",
        choices=("keep", "uninstall"),
        dest="system_versions",
        help=(
            "How to handle a system-wide tool version when a user-local copy is installed: "
            "'uninstall' removes it without prompting, 'keep' only warns. Prompts when unset."
        ),
    )

    paths = parser.add_argument_group("paths")
    paths.add_argument(
        "--windows-terminal-cwd",
        help="Optional Windows terminal cwd for VS Code (user-specific). Example: D:\\Workspace",
    )
    paths.add_argument(
        "--wsl-terminal-cwd",
        help=(
            "Optional WSL startup cwd for terminal profiles and WezTerm config "
            "(user-specific). Example: $HOME/workspace"
        ),
    )
    return parser


def _report_status(runner: Runner, label: str, ok: bool, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    if ok:
        runner.reporter.success(f"{label}{suffix}")
        return
    runner.reporter.warn(f"{label}{suffix}")


WINDOWS_RUNTIMES = ("uv", "python", "node")
VERSION_FLAGS = {"tmux": "-V"}
NO_VERSION = frozenset({"img-zoom"})
SHELL_TOOLS = (
    "zsh",
    "tmux",
    "git",
    "lazygit",
    "git-lfs",
    "direnv",
    "fzf",
    "fd",
    "bat",
    "rg",
    "jq",
    "yq",
    "shellcheck",
    "tree",
    "xh",
    "ast-grep",
    "sd",
    "just",
    "delta",
    "typos",
    "uv",
    "img-zoom",
    "python3",
    "node",
)
TOOL_MISSING = 127
RUNTIME_TARGETS = {
    "python": (prerequisites.python_meets_target, prerequisites.TARGET_PYTHON_MINOR),
    "python3": (prerequisites.python_meets_target, prerequisites.TARGET_PYTHON_MINOR),
    "node": (prerequisites.node_meets_target, f"v{prerequisites.TARGET_NODE_MAJOR}"),
}


def _target_status(command: str, version: str, detail: str) -> tuple[bool, str]:
    target = RUNTIME_TARGETS.get(command)
    if target is None:
        return True, detail
    meets, minimum = target
    if meets(version):
        return True, detail
    return False, f"{detail}, below the target {minimum}"


def _report_tool(runner: Runner, label: str, command: str, path: str, version: str) -> None:
    if not path:
        _report_status(runner, label, False, "")
        return
    ok, detail = _target_status(command, version, f"{path}, {version}" if version else path)
    _report_status(runner, label, ok, detail)


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0].strip() if lines else ""


def _windows_tool_info(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> tuple[str, str, str] | None:
    path = runner.which(command)
    note = ""
    if path is None:
        local = platform_info.home / ".local" / "bin" / f"{command}.exe"
        if not local.exists():
            return None
        path = str(local)
        note = ", restart terminal for PATH"
    result = runner.run([path, "--version"], check=False, dry_run_safe=True)
    version = _first_line(result.stdout or result.stderr or "") or "version unreadable"
    scope = "user profile" if prerequisites.is_user_scope(path, platform_info) else "machine-wide"
    return path, version, f"{scope}{note}"


def _windows_tool_detail(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> str | None:
    info = _windows_tool_info(runner, platform_info, command)
    return None if info is None else ", ".join(info)


def _report_optional_agent(runner: Runner, label: str, detail: str | None) -> None:
    agent = label.rsplit(":", 1)[-1]
    _report_optional(runner, label, detail, f"--agents {agent}")


def _report_optional(runner: Runner, label: str, detail: str | None, option: str) -> None:
    if detail:
        runner.reporter.success(f"{label} ({detail})")
        return
    runner.reporter.info(
        f"{label}: not installed (optional; to install it, run: {setup_command(option)})"
    )


def _report_herdr_integrations(
    runner: Runner, platform_info: platform.PlatformInfo, side: str
) -> None:
    states = agents.herdr_integration_states(runner, platform_info)
    for agent in agents.AGENTS:
        label = f"{side}:herdr-{agent}"
        state = states.get(agent, "not installed")
        if state.startswith("current"):
            runner.reporter.success(f"{label} ({state})")
        elif state.startswith("not installed"):
            _report_optional(runner, label, None, f"--herdr --agents {agent}")
        else:
            runner.reporter.warn(
                f"{label} ({state}; to update it, run: "
                f"{setup_command(f'--update --herdr --agents {agent}')})"
            )


def _shell_agent_path(runner: Runner, agent: str, *, wsl_distro: str | None) -> str | None:
    script = agents.present_query(agent) + '; echo "$found"'
    command = ["sh", "-c", script]
    if wsl_distro and not is_running_in_wsl():
        command = wsl_exec_command(wsl_distro, command)
    result = runner.run(command, check=False, dry_run_safe=True)
    found = result.stdout.strip()
    return found if result.returncode == 0 and found else None


def _probe_script(locate: str, command: str) -> str:
    flag = VERSION_FLAGS.get(command, "--version")
    probe = (
        "exit 0"
        if command in NO_VERSION
        else f'out=$("$p" {flag} </dev/null 2>&1); s=$?; printf "%s\\n" "$out" | head -n 1; exit $s'
    )
    return f'p={locate}; test -n "$p" || exit {TOOL_MISSING}; {probe}'


def _shell_tool_runs(
    runner: Runner, locate: str, command: str, *, wsl_distro: str | None
) -> tuple[bool | None, str]:
    script = ["sh", "-c", _probe_script(locate, command)]
    if wsl_distro and not is_running_in_wsl():
        script = wsl_exec_command(wsl_distro, script)
    result = runner.run(script, check=False, dry_run_safe=True)
    line = _first_line(result.stdout or result.stderr or "")
    if result.returncode == TOOL_MISSING and not line:
        return None, "not found"
    return result.returncode == 0, line or f"exit code {result.returncode}"


def _shell_locate(command: str) -> str:
    return (
        f"$(if test -x ~/.local/bin/{command}; then echo ~/.local/bin/{command}; "
        f"else command -v {command} || true; fi)"
    )


def _windows_tool_runs(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> tuple[bool | None, str]:
    path = runner.which(command)
    if path is None:
        for local in (
            platform_info.terminal_tools_dir / f"{command}.exe",
            platform_info.home / ".local" / "bin" / f"{command}.exe",
        ):
            if local.exists():
                path = str(local)
                break
    if path is None:
        return None, "not found"
    return _windows_path_runs(runner, path)


def _windows_path_runs(runner: Runner, path: str) -> tuple[bool, str]:
    result = runner.run([path, "--version"], check=False, dry_run_safe=True)
    line = _first_line(result.stdout or result.stderr or "")
    return result.returncode == 0, line or f"exit code {result.returncode}"


def _record_tool_run(
    runner: Runner, label: str, outcome: tuple[bool | None, str], *, missing_ok: bool
) -> None:
    ok, line = outcome
    if ok is None and missing_ok:
        runner.reporter.info(f"{label}: not installed")
        return
    if ok:
        runner.reporter.success(f"{label} runs ({line})" if line else f"{label} runs")
        return
    runner.failures.append(f"run {label}")
    runner.reporter.warn(f"{label} does not run: {line}")


def verify_tools_run(  # noqa: PLR0913
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
    selected_agents: Sequence[str],
    herdr: bool,
    no_sudo: bool,
) -> None:
    runner.reporter.step("Checking that each installed tool runs")
    in_wsl = is_running_in_wsl()
    windows_host = platform_info.os == platform.OperatingSystem.WINDOWS and not in_wsl
    shell_side = in_wsl or windows_host
    commands: list[str] = list(SHELL_TOOLS) if shell_side else ["wezterm", *SHELL_TOOLS]
    if include_starship:
        commands.append("starship")
    if herdr:
        commands.append("herdr")
    distro = (platform_info.wsl_distribution or "Ubuntu") if windows_host else None
    side = "wsl" if shell_side else "host"
    for command in commands:
        outcome = _shell_tool_runs(runner, _shell_locate(command), command, wsl_distro=distro)
        _record_tool_run(runner, f"{side}:{command}", outcome, missing_ok=no_sudo)
    for agent in selected_agents:
        found = _shell_agent_path(runner, agent, wsl_distro=distro)
        outcome = (
            _shell_tool_runs(runner, shlex.quote(found), agent, wsl_distro=distro)
            if found
            else (None, "not found")
        )
        _record_tool_run(runner, f"{side}:{agent}", outcome, missing_ok=False)
    if not windows_host:
        return
    tools = [tool.command for tool in windows_tools.WINDOWS_TOOLS]
    if include_starship:
        tools.append(windows_tools.STARSHIP.command)
    for command in (*tools, *WINDOWS_RUNTIMES):
        outcome = _windows_tool_runs(runner, platform_info, command)
        _record_tool_run(runner, f"windows:{command}", outcome, missing_ok=False)
    for agent in selected_agents:
        found = agents.windows_agent_path(runner, platform_info, agent)
        outcome = _windows_path_runs(runner, found) if found else (None, "not found")
        _record_tool_run(runner, f"windows:{agent}", outcome, missing_ok=False)


def _wsl_command_info(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> tuple[str, str]:
    version_step = (
        ""
        if command in NO_VERSION
        else f'; "$p" {VERSION_FLAGS.get(command, "--version")} </dev/null 2>&1 | head -n 1'
    )
    script = (
        f"p=$(if test -x ~/.local/bin/{command}; then echo ~/.local/bin/{command}; "
        f"else command -v {command} || true; fi); "
        f'test -n "$p" || exit 0; echo "$p"{version_step}'
    )
    if is_running_in_wsl():
        result = runner.run(
            ["sh", "-c", script],
            check=False,
            dry_run_safe=True,
        )
    else:
        distro = platform_info.wsl_distribution or "Ubuntu"
        result = runner.run(
            wsl_exec_command(distro, ["sh", "-c", script]),
            check=False,
            dry_run_safe=True,
        )
    lines = result.stdout.strip().splitlines()
    path = lines[0].strip() if lines else ""
    version = lines[1].strip() if len(lines) > 1 else ""
    return path, version


def _wsl_command_present(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> tuple[bool, str]:
    path, version = _wsl_command_info(runner, platform_info, command)
    return bool(path), f"{path}, {version}" if path and version else path


def _wsl_file_exists(
    runner: Runner, platform_info: platform.PlatformInfo, path: str
) -> tuple[bool, str]:
    if is_running_in_wsl():
        result = runner.run(
            ["sh", "-c", f"test -f {path}"],
            check=False,
            dry_run_safe=True,
        )
    else:
        distro = platform_info.wsl_distribution or "Ubuntu"
        result = runner.run(
            wsl_exec_command(distro, ["sh", "-c", f"test -f {path}"]),
            check=False,
            dry_run_safe=True,
        )
    return result.returncode == 0, path


def _print_windows_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
) -> None:
    for command in ["wezterm"]:
        path = runner.which(command)
        if path is None:
            for directory in prerequisites.windows_tool_candidate_dirs(platform_info, command):
                executable = directory / f"{command}.exe"
                if executable.exists():
                    path = f"{executable} (restart terminal for PATH)"
                    break
        _report_status(runner, f"windows:{command}", path is not None, path or "")

    tools = windows_tools.WINDOWS_TOOLS
    if include_starship:
        tools = (*tools, windows_tools.STARSHIP)
    for tool in tools:
        _report_windows_tool(runner, platform_info, tool)

    for command in WINDOWS_RUNTIMES:
        info = _windows_tool_info(runner, platform_info, command)
        if info is None:
            _report_status(runner, f"windows:{command}", False, "not found")
            continue
        ok, detail = _target_status(command, info[1], ", ".join(info))
        _report_status(runner, f"windows:{command}", ok, detail)
    for agent in agents.AGENTS:
        _report_optional_agent(
            runner, f"windows:{agent}", _windows_tool_detail(runner, platform_info, agent)
        )

    img_zoom = runner.which("img-zoom")
    local_img_zoom = platform_info.home / ".local" / "bin" / "img-zoom.exe"
    if img_zoom is None and local_img_zoom.exists():
        img_zoom = f"{local_img_zoom} (restart terminal for PATH)"
    _report_status(runner, "windows:img-zoom", img_zoom is not None, img_zoom or "")
    skill = platform_info.home / ".claude" / "skills" / "img-zoom" / "SKILL.md"
    _report_status(runner, "windows:~/.claude/skills/img-zoom/SKILL.md", skill.exists(), str(skill))

    if platform_info.wezterm_config_dir is not None:
        wezterm_path = platform_info.wezterm_config_dir / "wezterm.lua"
        _report_status(
            runner,
            "windows:wezterm.lua",
            wezterm_path.exists(),
            str(wezterm_path),
        )


def _report_windows_tool(
    runner: Runner, platform_info: platform.PlatformInfo, tool: windows_tools.WindowsTool
) -> None:
    label = f"windows:{tool.command}"
    path = runner.which(tool.command)
    note = ""
    local = platform_info.terminal_tools_dir / f"{tool.command}.exe"
    if path is None and local.exists():
        path, note = str(local), ", restart terminal for PATH"
    if path is None:
        _report_status(runner, label, False, "not found")
        return
    result = runner.run([path, "--version"], check=False, dry_run_safe=True)
    version = _first_line(result.stdout or result.stderr or "") or "version unreadable"
    origin = windows_tools.ORIGIN_LABELS[windows_tools.classify(path, platform_info, tool)]
    _report_status(runner, label, True, f"{path}, {version}, {origin}{note}")
    for hidden in windows_tools.all_copies(tool.command, platform_info)[1:]:
        if windows_tools.winget_package_dir(hidden) is not None:
            _report_status(
                runner,
                f"{label}: unused winget copy at {hidden}",
                False,
                f"remove it with: {setup_command('--winget-versions replace')}",
            )


def _print_wsl_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
) -> None:
    for command in SHELL_TOOLS:
        path, version = _wsl_command_info(runner, platform_info, command)
        _report_tool(runner, f"wsl:{command}", command, path, version)
    if include_starship:
        path, version = _wsl_command_info(runner, platform_info, "starship")
        _report_tool(runner, "wsl:starship", "starship", path, version)
    for path in [
        "~/.local/bin/fd",
        "~/.local/bin/bat",
        "~/.tmux.conf",
        "~/.zshrc",
        "~/.config/starship.toml",
        "~/.config/micro/settings.json",
        "~/.claude/statusline.sh",
        "~/.claude/skills/img-zoom/SKILL.md",
    ]:
        ok, detail = _wsl_file_exists(runner, platform_info, path)
        _report_status(runner, f"wsl:{path}", ok, detail)
    distro = None if is_running_in_wsl() else (platform_info.wsl_distribution or "Ubuntu")
    for agent in agents.AGENTS:
        _report_optional_agent(
            runner, f"wsl:{agent}", _shell_agent_path(runner, agent, wsl_distro=distro)
        )
    ok, detail = _wsl_command_present(runner, platform_info, "herdr")
    _report_optional(runner, "wsl:herdr", detail if ok else None, "--herdr")
    if ok:
        _report_herdr_integrations(runner, platform_info, "wsl")


def _host_command_path(runner: Runner, command: str) -> str | None:

    local = Path.home() / ".local" / "bin" / command
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return runner.which(command)


def _host_version(runner: Runner, command: str, path: str) -> str:
    if command in NO_VERSION:
        return ""
    flag = VERSION_FLAGS.get(command, "--version")
    result = runner.run([path, flag], check=False, dry_run_safe=True)
    return _first_line(result.stdout or result.stderr or "")


def _print_host_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
) -> None:
    for command in ("wezterm", *SHELL_TOOLS):
        path = _host_command_path(runner, command)
        version = _host_version(runner, command, path) if path else ""
        _report_tool(runner, f"host:{command}", command, path or "", version)
    if include_starship:
        path = _host_command_path(runner, "starship")
        version = _host_version(runner, "starship", path) if path else ""
        _report_tool(runner, "host:starship", "starship", path or "", version)
    for agent in agents.AGENTS:
        _report_optional_agent(
            runner, f"host:{agent}", _shell_agent_path(runner, agent, wsl_distro=None)
        )
    herdr = _host_command_path(runner, "herdr")
    _report_optional(runner, "host:herdr", herdr, "--herdr")
    if herdr:
        _report_herdr_integrations(runner, platform_info, "host")


def print_setup_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
    include_vscode: bool,
) -> None:
    runner.reporter.step("Verification report")

    in_wsl = is_running_in_wsl()
    if platform_info.os == platform.OperatingSystem.WINDOWS:
        _print_windows_report(runner, platform_info, include_starship=include_starship)

    if in_wsl or platform_info.os == platform.OperatingSystem.WINDOWS:
        _print_wsl_report(runner, platform_info, include_starship=include_starship)
    else:
        _print_host_report(runner, platform_info, include_starship=include_starship)

    if include_vscode and platform_info.os == platform.OperatingSystem.WINDOWS:
        vscode_path = platform_info.vscode_settings_path
        if vscode_path is not None:
            _report_status(
                runner,
                "vscode:settings.json",
                vscode_path.exists(),
                str(vscode_path),
            )


STATUS_SIDE_ENV = "TERMINAL_STATUS_SIDE"


def _release_state_version(command: str, version: str, state_dir: Path) -> str:
    recorded = state_dir / command
    if not version or not recorded.is_file():
        return version
    tag, _, printed = recorded.read_text(encoding="utf-8").strip().partition(" ")
    return tag if printed and printed in version else version


def _status_host(runner: Runner) -> list[tool_status.Installed | None]:
    items: list[tool_status.Installed | None] = []
    for command in ("wezterm", *SHELL_TOOLS, "starship", "herdr"):
        path = _host_command_path(runner, command)
        version = _host_version(runner, command, path) if path else ""
        version = _release_state_version(command, version, release_install.STATE_DIR)
        items.append(tool_status.Installed(command, path or "", version))
    return items


def _status_wsl(
    runner: Runner, platform_info: platform.PlatformInfo
) -> list[tool_status.Installed | None]:
    items: list[tool_status.Installed | None] = []
    for command in (*SHELL_TOOLS, "starship", "herdr"):
        path, version = _wsl_command_info(runner, platform_info, command)
        items.append(tool_status.Installed(command, path, version))
    return items


def _status_windows(
    runner: Runner, platform_info: platform.PlatformInfo
) -> list[tool_status.Installed | None]:
    items: list[tool_status.Installed | None] = []
    commands = (
        "wezterm",
        *(tool.command for tool in windows_tools.WINDOWS_TOOLS),
        windows_tools.STARSHIP.command,
        *WINDOWS_RUNTIMES,
    )
    for command in commands:
        info = _windows_tool_info(runner, platform_info, command)
        items.append(
            tool_status.Installed(command, info[0], info[1])
            if info
            else tool_status.Installed(command, "", "")
        )
    return items


def _apt_latest(runner: Runner, platform_info: platform.PlatformInfo, side: str) -> dict[str, str]:
    if side not in {"WSL", "Linux"}:
        return {}
    script = ["sh", "-c", f"apt-cache policy {' '.join(tool_status.APT_TOOLS)} 2>/dev/null"]
    if side == "WSL" and not is_running_in_wsl():
        script = wsl_exec_command(platform_info.wsl_distribution or "Ubuntu", script)
    result = runner.run(script, check=False, dry_run_safe=True)
    return tool_status.apt_candidates(result.stdout or "")


def _print_status_side(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    side: str,
    items: list[tool_status.Installed | None],
    lookups: tool_status.Lookups,
) -> None:
    commands = [item.command for item in items if item is not None]
    latest = {
        **_apt_latest(runner, platform_info, side),
        **tool_status.latest_versions(commands, lookups),
    }
    table_rows = tool_status.rows(items, commands, latest, NO_VERSION)
    for line in tool_status.table(side, table_rows):
        print(line)


def print_status(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    lookups: tool_status.Lookups | None = None,
) -> int:
    lookups = lookups or tool_status.Lookups()
    in_wsl = is_running_in_wsl()
    windows_host = platform_info.os == platform.OperatingSystem.WINDOWS and not in_wsl
    if windows_host:
        _print_status_side(
            runner, platform_info, "Windows", _status_windows(runner, platform_info), lookups
        )
        if os.environ.get(STATUS_SIDE_ENV) != "windows":
            _print_status_side(
                runner, platform_info, "WSL", _status_wsl(runner, platform_info), lookups
            )
        return 0
    side = "WSL" if in_wsl else "Linux"
    if platform_info.os == platform.OperatingSystem.MACOS:
        side = "macOS"
    _print_status_side(runner, platform_info, side, _status_host(runner), lookups)
    return 0


def run_check(platform_info: platform.PlatformInfo, runner: Runner) -> int:
    statuses = prerequisites.check_all(platform_info, runner)
    all_present = True
    for status in statuses:
        if status.present:
            runner.reporter.success(f"{status.name}: {status.message}")
        else:
            all_present = False
            runner.reporter.warn(f"{status.name}: {status.message}")
    if not all_present:
        runner.reporter.error("Some prerequisites are missing.")
        runner.reporter.step(f"Install the missing items named above, then run: {rerun_command()}")
        return 1
    runner.reporter.success("All prerequisites are satisfied.")
    return 0


def run_setup(  # noqa: PLR0912, PLR0913, PLR0915
    platform_info: platform.PlatformInfo,
    runner: Runner,
    *,
    skip_vscode: bool,
    skip_starship: bool,
    skip_claude: bool,
    no_nerd_font: bool,
    config_only: bool,
    system_install: bool,
    user_install: bool,
    update: bool = False,
    no_sudo: bool = False,
    selected_agents: tuple[str, ...] = (),
    herdr: bool = False,
    winget_versions: str | None = None,
    uninstall_system_versions: bool,
    keep_system_versions: bool,
    report: bool,
    windows_terminal_cwd: str | None,
    wsl_terminal_cwd: str | None,
) -> int:
    runner.reporter.info(f"Detected platform: {platform_info.os.name}")
    runner.reporter.info(f"Package manager: {platform_info.package_manager.name.lower()}")

    in_wsl = is_running_in_wsl()
    targets_wsl = platform_info.os == platform.OperatingSystem.WINDOWS or in_wsl
    effective_no_sudo = False if system_install else (no_sudo or user_install or targets_wsl)

    if config_only:
        runner.reporter.info(
            "Config-only mode: applying configuration without installing packages."
        )
    elif system_install:
        runner.reporter.info("System-install mode: installing tools system-wide (needs admin/sudo)")
    elif effective_no_sudo:
        runner.reporter.info("Installing tools into user-writable locations (no admin rights)")
    if user_install:
        runner.reporter.warn(
            "--user-install is deprecated: a user-local install is the default now, "
            "so the flag is a no-op."
        )

    if not config_only:
        runner.reporter.step("Installing tools")
        if in_wsl or platform_info.os == platform.OperatingSystem.WINDOWS:
            if in_wsl:
                runner.reporter.info(
                    "Running inside WSL; installing tools into the current distro."
                )
            prerequisites.attempt(
                runner,
                "install WSL system packages",
                partial(
                    prerequisites.ensure_wsl_system_packages,
                    runner,
                    platform_info,
                    allow_sudo=not no_sudo,
                    assume_yes=system_install,
                    upgrade=update,
                ),
            )
            prerequisites.ensure_wsl_tools(
                runner,
                platform_info,
                no_sudo=effective_no_sudo,
                update=update,
                uninstall_system_versions=uninstall_system_versions,
                keep_system_versions=keep_system_versions,
            )
            prerequisites.attempt(
                runner,
                "install WSL CLI extras",
                partial(prerequisites.ensure_wsl_cli_extras, runner, platform_info),
            )
        else:
            prerequisites.ensure_shell_tools(runner, platform_info, no_sudo=effective_no_sudo)
            prerequisites.ensure_host_cli_extras(runner, platform_info, no_sudo=effective_no_sudo)

        if platform_info.os == platform.OperatingSystem.WINDOWS and not in_wsl:
            prerequisites.attempt(
                runner,
                "install img-zoom in WSL",
                partial(configs.install_img_zoom_wsl, runner, platform_info, update=update),
            )
        prerequisites.attempt(
            runner,
            "install img-zoom",
            partial(configs.install_img_zoom_native, runner, platform_info, update=update),
        )

        prerequisites.attempt(
            runner,
            "install WezTerm",
            partial(
                prerequisites.ensure_wezterm,
                runner,
                platform_info,
                no_sudo=effective_no_sudo,
                update=update,
            ),
        )

        if platform_info.os == platform.OperatingSystem.WINDOWS and not in_wsl:
            windows_tools.ensure_windows_tools(
                runner,
                platform_info,
                update=update,
                policy=winget_versions,
                include_starship=not skip_starship,
            )
            prerequisites.attempt(
                runner,
                "check uv on Windows",
                partial(prerequisites.ensure_uv_windows, runner, platform_info, update=update),
            )

        prerequisites.attempt(
            runner,
            "install Python",
            partial(prerequisites.ensure_python, runner, platform_info, update=update),
        )

        prerequisites.attempt(
            runner,
            "install Node.js",
            partial(prerequisites.ensure_node, runner, platform_info, update=update),
        )

        agents.ensure_agents(runner, platform_info, selected_agents, update=update)
        if selected_agents:
            prerequisites.attempt(
                runner,
                "install the agents command",
                partial(agents.deploy_agents_command, runner, platform_info),
            )
        prerequisites.attempt(
            runner,
            "install the terminal command",
            partial(terminal_command.deploy_terminal_command, runner, platform_info),
        )

        if herdr:
            prerequisites.attempt(
                runner,
                "install herdr",
                partial(prerequisites.ensure_herdr, runner, platform_info, update=update),
            )
            agents.ensure_herdr_integrations(runner, platform_info, selected_agents)

        if not skip_starship:
            prerequisites.attempt(
                runner,
                "install starship",
                partial(prerequisites.ensure_starship, runner, platform_info, update=update),
            )

    runner.reporter.step("Deploying configuration")
    configs.deploy_all(
        runner,
        platform_info,
        include_starship=not skip_starship,
        include_claude=not skip_claude,
        claude_nerdfont=not no_nerd_font,
        no_sudo=no_sudo,
        wsl_start_dir=wsl_terminal_cwd,
        herdr=herdr or prerequisites.herdr_installed(runner, platform_info),
    )

    if not skip_vscode and platform_info.os == platform.OperatingSystem.WINDOWS:
        if not config_only:
            configs.install_vscode_wsl_extension(runner, platform_info)
        configs.configure_vscode_terminal(
            runner,
            platform_info,
            windows_terminal_cwd=windows_terminal_cwd,
            wsl_terminal_cwd=wsl_terminal_cwd,
        )

    if not config_only and not runner.dry_run:
        verify_tools_run(
            runner,
            platform_info,
            include_starship=not skip_starship,
            selected_agents=selected_agents,
            herdr=herdr,
            no_sudo=no_sudo,
        )

    if report:
        print_setup_report(
            runner,
            platform_info,
            include_starship=not skip_starship,
            include_vscode=not skip_vscode,
        )

    if runner.failures:
        runner.reporter.error(
            f"Setup finished with {len(runner.failures)} failed "
            f"{'step' if len(runner.failures) == 1 else 'steps'}:"
        )
        for failure in runner.failures:
            runner.reporter.error(f"  - {failure}")
        runner.reporter.step(f"Everything else was applied. To retry them, run: {rerun_command()}")
        return 1

    runner.reporter.success("Setup complete.")
    wezterm = prerequisites.wezterm_location(runner, platform_info)
    if wezterm:
        runner.reporter.step(f"WezTerm is installed at {wezterm}")
    if config_only:
        runner.reporter.step("Reload your shell or WezTerm to pick up the new configuration.")
    else:
        if platform_info.os == platform.OperatingSystem.WINDOWS:
            runner.reporter.step("Restart your terminal for the updated PATH to take effect.")
        if in_wsl:
            runner.reporter.step("Restart your WSL session for the updated PATH to take effect.")
            runner.reporter.step(
                "The Windows host was not changed. To install the Windows tools, run in "
                f"PowerShell: {platform.WINDOWS_BOOTSTRAP}"
            )
    runner.reporter.step(f"Verify anytime with: {setup_command('--only report')}")
    return 0


def main(argv: list[str] | None = None) -> int:

    os.environ["PATH"] = platform.path_without_own_environment(
        os.environ.get("PATH", ""), sys.executable, in_virtualenv=sys.prefix != sys.base_prefix
    )
    if sys.platform == "win32" and "PSMODULEPATH" in os.environ:
        os.environ["PSMODULEPATH"] = platform.windows_powershell_module_path(
            os.environ["PSMODULEPATH"]
        )
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = ConsoleReporter()
    runner = Runner(dry_run=args.dry_run, reporter=reporter, unattended=args.unattended)
    try:
        return _dispatch(args, runner)
    except KeyboardInterrupt:
        reporter.error("Interrupted.")
        return 130
    except subprocess.CalledProcessError as error:
        reporter.error(f"Command failed with exit code {error.returncode}: {error.cmd}")
        stderr = (error.stderr or "").strip()
        stdout = (error.stdout or "").strip()
        if stderr:
            reporter.error(stderr)
        elif stdout:
            reporter.error(stdout)
        reporter.step(f"Preview the failing step with: {setup_command('--dry-run')}")
        return 1
    except (RuntimeError, ValueError, OSError) as error:
        reporter.error(str(error))
        return 1


def _dispatch(args: argparse.Namespace, runner: Runner) -> int:
    platform_info = platform.detect_platform()

    if args.only == "check":
        return run_check(platform_info, runner)

    if args.only == "status":
        return print_status(runner, platform_info)

    if args.only == "report":
        status = run_check(platform_info, runner)
        print_setup_report(
            runner,
            platform_info,
            include_starship=not args.skip_starship,
            include_vscode=not args.skip_vscode,
        )
        return status

    config_only = args.only == "config"
    if not config_only:
        status = run_check(platform_info, runner)
        if status != 0:
            if args.dry_run:
                runner.reporter.info("Dry-run continues; missing prerequisites would be installed.")
            else:
                return status

    return run_setup(
        platform_info,
        runner,
        skip_vscode=args.skip_vscode,
        skip_starship=args.skip_starship,
        skip_claude=args.skip_claude,
        no_nerd_font=args.no_nerd_font,
        config_only=config_only,
        system_install=args.system_install,
        user_install=args.user_install,
        update=args.update,
        no_sudo=args.no_sudo,
        selected_agents=args.agents,
        herdr=args.herdr,
        winget_versions=args.winget_versions,
        uninstall_system_versions=args.system_versions == "uninstall",
        keep_system_versions=args.system_versions == "keep",
        report=args.report,
        windows_terminal_cwd=args.windows_terminal_cwd,
        wsl_terminal_cwd=args.wsl_terminal_cwd,
    )


if __name__ == "__main__":
    sys.exit(main())
