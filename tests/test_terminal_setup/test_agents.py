from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import agents
from terminal_setup.agents import (
    AGENTS,
    CLAUDE_INSTALL_PS1,
    SHELL_INSTALL_SCRIPTS,
    ensure_agents,
    parse_agents,
    present_query,
    shell_install_script,
    shell_update_script,
)
from terminal_setup.cli import build_parser
from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    wsl_exec_command,
)

from ..conftest import guarded_system_path
from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("all", AGENTS),
        ("claude", ("claude",)),
        ("Codex, claude,codex", ("codex", "claude")),
    ],
)
def test_parse_agents(value: str, expected: tuple[str, ...]) -> None:
    assert parse_agents(value) == expected


@pytest.mark.parametrize("value", ["gemini", "claude,cursor", ""])
def test_parse_agents_refuses_an_unknown_name(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="choose from claude, copilot, codex"):
        parse_agents(value)


def test_agents_flag_defaults_to_none() -> None:
    assert build_parser().parse_args([]).agents == ()
    assert build_parser().parse_args(["--agents", "all"]).agents == AGENTS


@pytest.mark.skipif(
    sys.platform == "win32", reason="the query runs in a POSIX sh inside WSL or on a Unix host"
)
@pytest.mark.parametrize(
    ("found", "present"),
    [("/home/dev/.local/bin/codex", 0), ("/mnt/c/Users/dev/nodejs/codex", 1), ("", 1)],
)
def test_present_query_ignores_a_windows_copy_seen_from_wsl(
    tmp_path: Path, found: str, present: int
) -> None:
    script = present_query("codex").replace("command -v codex", f"echo {found}; test -n '{found}'")
    result = subprocess.run(["sh", "-c", script], check=False, cwd=tmp_path)

    assert result.returncode == present


def _wsl(script: str) -> list[str]:
    return wsl_exec_command("Ubuntu", ["sh", "-c", script])


def _linux_platform() -> PlatformInfo:
    return replace(
        _windows_platform(), os=OperatingSystem.LINUX, package_manager=PackageManager.APT
    )


def _run_shell(
    selected: tuple[str, ...], *, update: bool, outputs: dict[tuple[str, ...], tuple[int, str]]
) -> RecordingRunner:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs=outputs)
    with (
        mock.patch.object(agents, "is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=True),
    ):
        ensure_agents(runner, _linux_platform(), selected, update=update)
    return runner


def _absent(*names: str) -> dict[tuple[str, ...], tuple[int, str]]:
    return {("sh", "-c", present_query(name)): (1, "") for name in names}


def test_shell_installs_only_the_selected_absent_agents() -> None:
    runner = _run_shell(("claude", "codex"), update=False, outputs=_absent(*AGENTS))

    installs = [command[-1] for command in runner.commands if "install" in command[-1]]
    assert installs == [shell_install_script("claude"), shell_install_script("codex")]


def test_shell_skips_a_present_agent() -> None:
    runner = _run_shell(AGENTS, update=False, outputs={})

    assert [command[-1] for command in runner.commands] == [present_query(a) for a in AGENTS]
    assert ("success", "codex is present on this host") in runner.reporter.messages  # type: ignore[attr-defined]


def test_shell_update_runs_the_self_update_of_each_present_agent() -> None:
    runner = _run_shell(("claude", "codex"), update=True, outputs={})

    scripts = [command[-1] for command in runner.commands]
    assert shell_update_script("claude") in scripts
    assert shell_update_script("codex") in scripts
    assert shell_update_script("copilot") in scripts


def test_an_agent_that_is_not_named_is_updated_when_present_and_never_installed() -> None:
    runner = _run_shell((), update=True, outputs=_absent("copilot"))

    scripts = [command[-1] for command in runner.commands]
    assert shell_update_script("claude") in scripts
    assert shell_update_script("codex") in scripts
    assert shell_install_script("copilot") not in scripts
    assert shell_update_script("copilot") not in scripts


def test_without_update_an_agent_that_is_not_named_is_left_alone() -> None:
    runner = _run_shell((), update=False, outputs={})

    assert runner.commands == []


def test_installed_agents_lists_the_present_agents() -> None:
    runner = RecordingRunner(reporter=CapturingReporter(), outputs=_absent("copilot"))

    with mock.patch.object(agents, "is_running_in_wsl", return_value=True):
        assert agents.installed_agents(runner, _linux_platform()) == ("claude", "codex")


def test_the_shell_installers_are_the_vendor_scripts() -> None:
    assert shell_install_script("claude") == "curl -fsSL https://claude.ai/install.sh | bash"
    assert shell_install_script("copilot") == "curl -fsSL https://gh.io/copilot-install | bash"
    assert shell_install_script("codex") == "curl -fsSL https://chatgpt.com/codex/install.sh | sh"
    assert "npm" not in " ".join(shell_install_script(agent) for agent in AGENTS)


def test_an_unattended_codex_install_answers_its_questions_with_no() -> None:
    assert shell_install_script("codex", unattended=True).endswith("| CODEX_NON_INTERACTIVE=1 sh")
    assert "CODEX_NON_INTERACTIVE = '1'" in agents.windows_codex_command(unattended=True)[-1]
    assert "CODEX_NON_INTERACTIVE" not in agents.windows_codex_command(unattended=False)[-1]


def test_shell_install_runs_in_wsl_from_a_windows_host(tmp_path: Path) -> None:
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={tuple(_wsl(present_query("copilot"))): (1, "")},
        has_sudo=False,
    )
    platform = replace(_windows_platform(), home=tmp_path)

    with (
        mock.patch.object(agents, "is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch.object(agents, "_windows_npm", return_value="C:/nodejs/npm.cmd"),
    ):
        ensure_agents(runner, platform, ("copilot",), update=False)

    assert _wsl(shell_install_script("copilot")) in runner.commands
    assert ["C:/nodejs/npm.cmd", "install", "-g", "@github/copilot"] in runner.commands


class WindowsAgentRunner(RecordingRunner):
    found: dict[str, str] = {}  # noqa: RUF012

    def which(self, command: str) -> str | None:
        return self.found.get(command)


def _run_windows(
    tmp_path: Path, selected: tuple[str, ...], found: dict[str, str], *, update: bool = False
) -> WindowsAgentRunner:
    runner = WindowsAgentRunner(reporter=CapturingReporter())
    runner.found = found
    platform = replace(_windows_platform(), home=tmp_path)
    with mock.patch("terminal_setup.prerequisites._add_to_process_path"):
        for agent in selected:
            agents._ensure_windows_agent(runner, platform, agent, update=update)
    return runner


def test_windows_installs_claude_with_its_native_installer(tmp_path: Path) -> None:
    runner = _run_windows(tmp_path, ("claude",), {})

    assert ["powershell", "-NoProfile", "-Command", CLAUDE_INSTALL_PS1] in runner.commands


def test_windows_npm_agent_without_npm_fails_by_name(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="npm is not on the Windows PATH"):
        _run_windows(tmp_path, ("copilot",), {})


def test_windows_installs_codex_with_its_vendor_script(tmp_path: Path) -> None:
    runner = _run_windows(tmp_path, ("codex",), {})

    assert runner.commands == [agents.windows_codex_command(unattended=False)]


def test_windows_finds_claude_in_the_local_bin_before_path_refresh(tmp_path: Path) -> None:
    local = tmp_path / ".local" / "bin" / "claude.exe"
    local.parent.mkdir(parents=True)
    local.write_bytes(b"")

    runner = _run_windows(tmp_path, ("claude",), {})

    assert runner.commands == []


def test_windows_update_runs_the_self_update_of_each_user_scope_agent(tmp_path: Path) -> None:
    claude = str(tmp_path / ".local" / "bin" / "claude.exe")
    codex = str(tmp_path / "AppData" / "Roaming" / "npm" / "codex.cmd")
    copilot = "C:/Program Files/GitHub Copilot/copilot.exe"

    runner = _run_windows(
        tmp_path, AGENTS, {"claude": claude, "codex": codex, "copilot": copilot}, update=True
    )

    assert runner.commands == [[claude, "update"], [codex, "update"]]
    assert any(
        level == "info" and copilot in message and "managed by your organisation" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_windows_failed_agent_update_names_the_manual_retry(tmp_path: Path) -> None:
    codex = str(tmp_path / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "codex.exe")
    runner = WindowsAgentRunner(reporter=CapturingReporter())
    runner.found = {"codex": codex}
    failing = subprocess.CalledProcessError(1, [codex, "update"])

    with (
        mock.patch.object(runner, "run", side_effect=failing),
        pytest.raises(subprocess.CalledProcessError),
    ):
        agents._ensure_windows_agent(
            runner, replace(_windows_platform(), home=tmp_path), "codex", update=True
        )

    assert ("step", "To retry, run 'codex update' in Windows PowerShell (powershell.exe).") in (
        runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_codex_is_found_where_its_windows_installer_puts_it(tmp_path: Path) -> None:
    platform = replace(_windows_platform(), home=tmp_path)
    codex = platform.user_programs_dir / "OpenAI" / "Codex" / "bin" / "codex.exe"
    codex.parent.mkdir(parents=True)
    codex.write_text("", encoding="utf-8")
    runner = RecordingRunner(reporter=CapturingReporter())

    with mock.patch.object(runner, "which", return_value=None):
        assert agents.windows_agent_path(runner, platform, "codex") == str(codex)


def _rendered(name: str) -> str:
    return agents.render_agents_command(name)


def test_the_agents_command_uses_only_the_installers_of_this_module() -> None:
    known = {
        *SHELL_INSTALL_SCRIPTS.values(),
        CLAUDE_INSTALL_PS1,
        agents.CODEX_INSTALL_PS1,
        *agents.LATEST_VERSION_URLS.values(),
    }
    allowed = {url for text in known for url in re.findall(r"https://[^\s\"'|/]+[^\s\"'|]*", text)}
    for name in agents.AGENTS_COMMAND_TEMPLATES:
        text = _rendered(name)
        assert re.search(r"__[A-Z0-9_]+__", text) is None
        found = {url.rstrip("/") for url in re.findall(r"https://[^\s\"'|$]+", text)}
        assert found <= {url.rstrip("/") for url in allowed}, name


def test_agents_cmd_falls_back_to_windows_powershell() -> None:
    text = _rendered("agents.cmd")

    assert "\r\n" in text
    assert text.count("\n") == text.count("\r\n")
    assert "where pwsh" in text
    assert 'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agents.ps1" %*' in text
    assert "exit /b %errorlevel%" in text


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="requires shellcheck")
def test_the_rendered_agents_script_passes_shellcheck(tmp_path: Path) -> None:
    script = tmp_path / "agents"
    script.write_text(_rendered("agents"), encoding="utf-8")

    result = subprocess.run(
        ["shellcheck", "-s", "bash", str(script)], check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stdout


def _bash4() -> str | None:
    bash = shutil.which("bash")
    if bash is None or sys.platform == "win32":
        return None
    probe = subprocess.run(
        [bash, "-c", "echo $BASH_VERSINFO"], check=False, capture_output=True, text=True
    )
    return bash if probe.stdout.strip().isdigit() and int(probe.stdout.strip()) >= 4 else None


needs_bash4 = pytest.mark.skipif(_bash4() is None, reason="runs the bash 4 agents script")

_LATEST = {"claude": "2.1.0", "codex": "0.171.0", "copilot": "1.0.5"}
_FAKE_CURL = """#!/bin/sh
for arg in "$@"; do url="$arg"; done
[ -n "$AGENTS_TEST_OFFLINE" ] && exit 22
case "$url" in
  *claude-code-releases/*) echo "$LATEST_CLAUDE" ;;
  *codex/channels/latest) printf '{"tag_name": "rust-v%s"}' "$LATEST_CODEX" ;;
  *copilot-cli/releases/latest)
    printf 'HTTP/2 302\\r\\nlocation: %s/tag/v%s\\r\\n' "$url" "$LATEST_COPILOT" ;;
  *install.sh)
    printf 'echo "installer=$CODEX_INSTALL_DAEMON_ONLY" >> "$AGENTS_TEST_LOG"\\n' ;;
  *) echo "unexpected url $url" >&2; exit 22 ;;
esac
"""


def _fake_agent(path: Path, version: str, *, daemon_update: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        f'echo "{path.name} $*" >> "$AGENTS_TEST_LOG"\n'
        f'[ "$1" = --version ] && echo "{version} ({path.name})"\n'
        f'[ "$1 $2 $3" = "app-server daemon update" ] && exit {daemon_update}\n'
        "exit 0\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _agents_home(tmp_path: Path, versions: dict[str, str]) -> Path:
    home = tmp_path / "home"
    for agent, version in versions.items():
        _fake_agent(home / ".local" / "bin" / agent, version)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    curl = stubs / "curl"
    curl.write_text(_FAKE_CURL, encoding="utf-8")
    curl.chmod(0o755)
    script = tmp_path / "agents"
    script.write_text(_rendered("agents"), encoding="utf-8")
    script.chmod(0o755)
    return home


def _run_agents(
    tmp_path: Path, *arguments: str, stdin: str = "", **extra: str
) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": guarded_system_path(tmp_path / "stubs"),
        "AGENTS_TEST_LOG": str(tmp_path / "calls.log"),
        "LATEST_CLAUDE": _LATEST["claude"],
        "LATEST_CODEX": _LATEST["codex"],
        "LATEST_COPILOT": _LATEST["copilot"],
        "AGENTS_TEST_OFFLINE": "",
        **extra,
    }
    return subprocess.run(
        [str(_bash4()), str(tmp_path / "agents"), *arguments, "--wsl"],
        check=False,
        capture_output=True,
        text=True,
        input=stdin,
        env=env,
    )


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _row(output: str, agent: str) -> list[str]:
    plain = re.sub(r"\x1b\[[0-9;]*m", "", output)
    return next(line.split() for line in plain.splitlines() if line.startswith(f"{agent} "))


@needs_bash4
def test_agents_status_compares_each_installed_version_with_the_latest(tmp_path: Path) -> None:
    home = _agents_home(tmp_path, {"claude": "2.1.0", "codex": "0.170.0"})
    daemon = home / ".codex" / "packages" / "app-server-daemon"
    (daemon / "0.171.0-x86_64-unknown-linux-musl").mkdir(parents=True)
    (daemon / "current").symlink_to(daemon / "0.171.0-x86_64-unknown-linux-musl")

    result = _run_agents(tmp_path, "status")

    assert result.returncode == 0, result.stdout
    assert _row(result.stdout, "claude") == ["claude", "2.1.0", "2.1.0", "ok"]
    assert _row(result.stdout, "codex") == ["codex", "0.170.0", "0.171.0", "update"]
    assert _row(result.stdout, "daemon") == ["daemon", "0.171.0", "0.171.0", "ok"]
    assert _row(result.stdout, "copilot") == ["copilot", "-", "1.0.5", "missing"]
    assert not any(call.endswith(" update") for call in _calls(tmp_path))


@needs_bash4
def test_agents_status_exits_zero_when_a_lookup_fails(tmp_path: Path) -> None:
    _agents_home(tmp_path, {"claude": "2.1.0"})

    result = _run_agents(tmp_path, "status", AGENTS_TEST_OFFLINE="1")

    assert result.returncode == 0, result.stdout
    assert _row(result.stdout, "claude") == ["claude", "2.1.0", "?", "unknown"]


@needs_bash4
def test_agents_update_runs_only_the_updaters_of_outdated_agents(tmp_path: Path) -> None:
    _agents_home(tmp_path, {"claude": "2.1.0", "codex": "0.170.0", "copilot": "1.0.5"})

    result = _run_agents(tmp_path, "update")

    calls = _calls(tmp_path)
    assert "codex update" in calls
    assert "claude update" not in calls
    assert "copilot update" not in calls
    assert "stops running Codex work" in result.stdout
    assert "codex app-server daemon update" in calls


@needs_bash4
def test_agents_update_with_force_runs_every_updater(tmp_path: Path) -> None:
    _agents_home(tmp_path, {"claude": "2.1.0", "codex": "0.171.0", "copilot": "1.0.5"})

    _run_agents(tmp_path, "update", "--force")

    calls = _calls(tmp_path)
    assert {"claude update", "codex update", "copilot update"} <= set(calls)


@needs_bash4
def test_a_failed_daemon_update_falls_back_to_the_daemon_only_installer(tmp_path: Path) -> None:
    home = _agents_home(tmp_path, {"claude": "2.1.0", "copilot": "1.0.5"})
    _fake_agent(home / ".local" / "bin" / "codex", "0.171.0", daemon_update=1)

    result = _run_agents(tmp_path, "update")

    assert result.returncode == 0, result.stdout
    assert "installer=1" in _calls(tmp_path)


@needs_bash4
@pytest.mark.parametrize(
    ("relative", "command"),
    [
        (
            "lib/node_modules/@anthropic-ai/claude-code/bin/claude",
            "npm install -g @anthropic-ai/claude-code@latest",
        ),
        ("linuxbrew/Cellar/claude-code/2.0.0/bin/claude", "brew upgrade claude-code"),
    ],
)
def test_agents_refuses_a_package_manager_install_by_name(
    tmp_path: Path, relative: str, command: str
) -> None:
    home = _agents_home(tmp_path, {"codex": "0.171.0", "copilot": "1.0.5"})
    real = tmp_path / relative
    _fake_agent(real, "2.0.0")
    (home / ".local" / "bin" / "claude").symlink_to(real)

    result = _run_agents(tmp_path, "update")

    assert result.returncode == 1
    assert f"Run: {command}" in result.stdout
    assert "claude update" not in _calls(tmp_path)


@needs_bash4
def test_agents_uninstall_removes_the_binaries_and_keeps_the_configuration(tmp_path: Path) -> None:
    home = _agents_home(tmp_path, {"claude": "2.1.0", "codex": "0.171.0", "copilot": "1.0.5"})
    kept = [
        home / ".claude" / "settings.json",
        home / ".codex" / "config.toml",
        home / ".copilot" / "config.json",
    ]
    for path in kept:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (home / ".local" / "share" / "claude" / "versions").mkdir(parents=True)
    (home / ".codex" / "packages" / "standalone").mkdir(parents=True)

    result = _run_agents(tmp_path, "uninstall", stdin="yes\n")

    assert result.returncode == 0, result.stdout
    for agent in ("claude", "codex", "copilot"):
        assert not (home / ".local" / "bin" / agent).exists()
    assert not (home / ".local" / "share" / "claude").exists()
    assert not (home / ".codex" / "packages").exists()
    assert all(path.exists() for path in kept)


@needs_bash4
def test_agents_uninstall_without_yes_removes_nothing(tmp_path: Path) -> None:
    home = _agents_home(tmp_path, {"claude": "2.1.0"})

    result = _run_agents(tmp_path, "uninstall", stdin="no\n")

    assert result.returncode == 1
    assert "Cancelled." in result.stdout
    assert (home / ".local" / "bin" / "claude").exists()


@needs_bash4
def test_agents_refuses_an_unknown_argument_with_the_usage(tmp_path: Path) -> None:
    _agents_home(tmp_path, {})

    result = _run_agents(tmp_path, "upgrade")

    assert result.returncode == 2
    assert "usage: agents <status|update|install|uninstall>" in result.stderr


def test_setup_writes_the_agents_command_on_linux(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform = replace(_linux_platform(), home=tmp_path)

    with mock.patch.object(agents, "is_running_in_wsl", return_value=False):
        agents.deploy_agents_command(runner, platform)

    target = tmp_path / ".local" / "bin" / "agents"
    assert target.read_text(encoding="utf-8") == _rendered("agents")
    if sys.platform != "win32":
        assert target.stat().st_mode & 0o111


def test_setup_writes_the_windows_agents_command_and_the_wsl_copy(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform = replace(_windows_platform(), home=tmp_path)

    with (
        mock.patch.object(agents, "is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._add_to_process_path"),
    ):
        agents.deploy_agents_command(runner, platform)

    bin_dir = tmp_path / ".local" / "bin"
    assert (bin_dir / "agents.ps1").read_text(encoding="utf-8") == _rendered("agents.ps1")
    assert (bin_dir / "agents.cmd").read_bytes() == _rendered("agents.cmd").encode()
    staged = tmp_path / ".local" / "share" / "terminal" / "agents"
    assert staged.read_text(encoding="utf-8") == _rendered("agents")
    assert any(
        command[:2] == ["wsl", "-d"] and str(staged) in command for command in runner.commands
    )


def test_setup_skips_the_agents_command_on_macos(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform = replace(_linux_platform(), os=OperatingSystem.MACOS, home=tmp_path)

    agents.deploy_agents_command(runner, platform)

    assert not (tmp_path / ".local" / "bin" / "agents").exists()


needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="runs agents.ps1 in pwsh")

_PWSH_WRAPPER = """
function Invoke-RestMethod {
  $url = "$args"
  if ($env:AGENTS_TEST_OFFLINE) { throw "offline" }
  if ($url -match "claude-code-releases") { return "2.1.0" }
  if ($url -match "codex/channels/latest") {
    return [pscustomobject]@{ tag_name = "rust-v0.171.0" }
  }
  if ($url -match "install.ps1") {
    return 'Add-Content $env:AGENTS_TEST_LOG "installer=$env:CODEX_INSTALL_DAEMON_ONLY"'
  }
  throw "unexpected $url"
}
function Invoke-WebRequest {
  if ($env:AGENTS_TEST_OFFLINE) { throw "offline" }
  $tag = "https://github.com/github/copilot-cli/releases/tag/v1.0.5"
  [pscustomobject]@{ Headers = @{ Location = $tag } }
}
$script = $args[0]
$rest = @($args | Select-Object -Skip 1)
& $script @rest
exit $LASTEXITCODE
"""


def _fake_windows_agent(
    directory: Path, name: str, version: str, *, daemon_update: int = 0
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        _fake_agent(directory / name, version, daemon_update=daemon_update)
        return
    (directory / f"{name}.cmd").write_text(
        "@echo off\r\n"
        f'>>"%AGENTS_TEST_LOG%" echo {name} %*\r\n'
        f'if "%1"=="--version" echo {version} ({name})\r\n'
        f'if "%1 %2 %3"=="app-server daemon update" exit /b {daemon_update}\r\n'
        "exit /b 0\r\n",
        encoding="utf-8",
    )


def _ps_home(tmp_path: Path) -> Path:
    profile = tmp_path / "profile"
    (profile / "AppData" / "Local").mkdir(parents=True)
    (tmp_path / "stubs").mkdir(exist_ok=True)
    (tmp_path / "agents.ps1").write_text(_rendered("agents.ps1"), encoding="utf-8")
    (tmp_path / "wrapper.ps1").write_text(_PWSH_WRAPPER, encoding="utf-8")
    return profile


def _run_ps(
    tmp_path: Path, *arguments: str, extra_path: Path | None = None, **extra: str
) -> subprocess.CompletedProcess[str]:
    pwsh = str(shutil.which("pwsh"))
    profile = tmp_path / "profile"
    parts = [
        str(tmp_path / "stubs"),
        *([str(extra_path)] if extra_path else []),
        str(Path(pwsh).parent),
    ]
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"CODEX_HOME", "AGENTS_CONFIRMED"}
    }
    env.update({
        "PATH": os.pathsep.join(parts),
        "USERPROFILE": str(profile),
        "HOME": str(profile),
        "LOCALAPPDATA": str(profile / "AppData" / "Local"),
        "AGENTS_TEST_LOG": str(tmp_path / "calls.log"),
        "AGENTS_TEST_OFFLINE": "",
        **extra,
    })
    return subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(tmp_path / "wrapper.ps1"),
            str(tmp_path / "agents.ps1"),
            *arguments,
            "--win",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _ps_calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    if not log.exists():
        return []
    return [line.strip() for line in log.read_text(encoding="utf-8", errors="replace").splitlines()]


@needs_pwsh
def test_agents_ps1_status_compares_each_installed_version_with_the_latest(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")
    _fake_windows_agent(tmp_path / "stubs", "codex", "0.170.0")

    result = _run_ps(tmp_path, "status")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _row(result.stdout, "claude") == ["claude", "2.1.0", "2.1.0", "ok"]
    assert _row(result.stdout, "codex") == ["codex", "0.170.0", "0.171.0", "update"]
    assert _row(result.stdout, "daemon") == ["daemon", "-", "0.171.0", "missing"]
    assert _row(result.stdout, "copilot") == ["copilot", "-", "1.0.5", "missing"]


@needs_pwsh
def test_agents_ps1_status_exits_zero_when_a_lookup_fails(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")

    result = _run_ps(tmp_path, "status", AGENTS_TEST_OFFLINE="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _row(result.stdout, "claude") == ["claude", "2.1.0", "?", "unknown"]


@needs_pwsh
def test_agents_ps1_update_runs_only_outdated_updaters_and_warns_before_the_daemon(
    tmp_path: Path,
) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")
    _fake_windows_agent(tmp_path / "stubs", "codex", "0.170.0")
    _fake_windows_agent(tmp_path / "stubs", "copilot", "1.0.5")

    result = _run_ps(tmp_path, "update")

    calls = _ps_calls(tmp_path)
    assert "codex update" in calls
    assert "claude update" not in calls
    assert "copilot update" not in calls
    assert "codex app-server daemon update" in calls
    assert "stops running Codex work" in result.stdout


@needs_pwsh
def test_agents_ps1_falls_back_to_the_daemon_only_installer(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")
    _fake_windows_agent(tmp_path / "stubs", "copilot", "1.0.5")
    _fake_windows_agent(tmp_path / "stubs", "codex", "0.171.0", daemon_update=1)

    result = _run_ps(tmp_path, "update")

    assert "installer=1" in _ps_calls(tmp_path), result.stdout + result.stderr


@needs_pwsh
def test_agents_ps1_refuses_an_npm_claude_and_updates_an_npm_copilot(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    prefix = tmp_path / "npm-prefix"
    _fake_windows_agent(prefix, "claude", "2.0.0")
    _fake_windows_agent(prefix, "copilot", "1.0.0")
    _fake_windows_agent(tmp_path / "stubs", "codex", "0.171.0")
    npm = tmp_path / "stubs" / ("npm.cmd" if sys.platform == "win32" else "npm")
    if sys.platform == "win32":
        npm.write_text(
            "@echo off\r\n"
            f'if "%1"=="prefix" (echo {prefix}& exit /b 0)\r\n'
            f'if "%1"=="root" (echo {prefix}\\node_modules& exit /b 0)\r\n'
            '>>"%AGENTS_TEST_LOG%" echo npm %*\r\n',
            encoding="utf-8",
        )
    else:
        npm.write_text(
            f'#!/bin/sh\ncase "$1" in prefix) echo "{prefix}";;\n'
            f'root) echo "{prefix}/node_modules";;\n'
            '*) echo "npm $*" >> "$AGENTS_TEST_LOG";; esac\n',
            encoding="utf-8",
        )
        npm.chmod(0o755)

    result = _run_ps(tmp_path, "update", extra_path=prefix)

    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert "Run: npm install -g @anthropic-ai/claude-code@latest" in output
    assert "claude update" not in _ps_calls(tmp_path)
    assert "npm install -g @github/copilot@latest" in _ps_calls(tmp_path)


@needs_pwsh
def test_agents_ps1_uninstall_removes_the_binaries_and_keeps_the_configuration(
    tmp_path: Path,
) -> None:
    profile = _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "codex", "0.171.0")
    removed = [
        profile / ".local" / "bin" / "claude.exe",
        profile / ".local" / "share" / "claude" / "versions" / "2.1.0",
        profile / ".codex" / "packages" / "standalone" / "current",
        profile / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe",
    ]
    kept = [
        profile / ".claude" / "settings.json",
        profile / ".codex" / "config.toml",
        profile / ".copilot" / "config.json",
    ]
    for path in [*removed, *kept]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    result = _run_ps(tmp_path, "uninstall", AGENTS_CONFIRMED="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (profile / ".local" / "bin" / "claude.exe").exists()
    assert not (profile / ".local" / "share" / "claude").exists()
    assert not (profile / ".codex" / "packages").exists()
    assert not (profile / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex").exists()
    assert all(path.exists() for path in kept)
    assert "codex app-server daemon stop" in _ps_calls(tmp_path)


@needs_bash4
def test_a_nested_agents_run_leaves_the_done_line_to_its_parent(tmp_path: Path) -> None:
    _agents_home(tmp_path, {"claude": "2.1.0", "codex": "0.171.0", "copilot": "1.0.5"})

    nested = _run_agents(tmp_path, "status", AGENTS_NESTED="1")
    alone = _run_agents(tmp_path, "status")

    assert nested.returncode == 0, nested.stdout
    assert "All done." not in nested.stdout
    assert alone.stdout.count("All done.") == 1


@needs_pwsh
def test_agents_ps1_prints_the_wsl_side_without_its_own_heading(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        wrapper.read_text(encoding="utf-8").replace(
            "@rest", "@($rest | Where-Object { $_ -ne '--win' })"
        ),
        encoding="utf-8",
    )

    result = _run_ps(tmp_path, "status")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "==> WSL" not in result.stdout
    assert result.stdout.count("All done.") == 1


@needs_pwsh
def test_a_nested_agents_ps1_run_leaves_the_done_line_to_its_parent(tmp_path: Path) -> None:
    _ps_home(tmp_path)
    _fake_windows_agent(tmp_path / "stubs", "claude", "2.1.0")

    result = _run_ps(tmp_path, "status", AGENTS_NESTED="1")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All done." not in result.stdout
