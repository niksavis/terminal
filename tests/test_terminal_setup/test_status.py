from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import agents, cli, status, terminal_command
from terminal_setup.cli import build_parser
from terminal_setup.platform import SETUP_ARCHIVES, OperatingSystem

from ..conftest import guarded_system_path
from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

LATEST = {
    "BurntSushi/ripgrep": "15.1.0",
    "sharkdp/fd": "v10.4.0",
    "wezterm/wezterm": "20240203-110809-5046fc22",
}


def _fake_release(repo: str) -> str:
    if repo not in LATEST:
        raise OSError("offline")
    return LATEST[repo]


FAKE = status.Lookups(release=_fake_release, node=lambda major: f"v{major}.2.0")


@pytest.mark.parametrize(
    ("text", "version"),
    [
        ("ripgrep 15.1.0", "15.1.0"),
        ("jq-1.8.1", "1.8.1"),
        ("yq (https://github.com/mikefarah/yq/) version v4.54.3", "4.54.3"),
        ("fdfind 10.3.0", "10.3.0"),
        ("tmux 3.6", "3.6"),
        ("ShellCheck - shell script analysis tool", ""),
        ("wezterm 20260707-093716-fff02ca5", "20260707-093716-fff02ca5"),
    ],
)
def test_version_of_reads_the_first_version_number(text: str, version: str) -> None:
    assert status.version_of(text) == version


@pytest.mark.parametrize(
    ("installed", "latest", "expected"),
    [
        (status.Installed("rg", "/bin/rg", "ripgrep 15.1.0"), "15.1.0", "ok"),
        (status.Installed("fd", "/bin/fd", "fdfind 10.3.0"), "v10.4.0", "update"),
        (status.Installed("fd", "/bin/fd", "fdfind 10.10.0"), "v10.9.0", "ok"),
        (status.Installed("fd", "", ""), "v10.4.0", "missing"),
        (None, "v10.4.0", "missing"),
        (status.Installed("rg", "/bin/rg", "ripgrep 15.1.0"), "", "unknown"),
        (
            status.Installed("wezterm", "/bin/wezterm", "wezterm 20240203-110809-5046fc22"),
            "20240203-110809-5046fc22",
            "ok",
        ),
    ],
)
def test_state_compares_the_installed_and_the_latest_version(
    installed: status.Installed | None, latest: str, expected: str
) -> None:
    assert status.state(installed, latest) == expected


def test_latest_versions_uses_the_lookups_and_reports_a_failed_one_as_empty() -> None:
    latest = status.latest_versions(["rg", "fd", "bat", "node", "python3"], FAKE)

    assert latest == {
        "rg": "15.1.0",
        "fd": "v10.4.0",
        "bat": "",
        "node": "v26.2.0",
        "python3": "3.14",
    }


def test_every_release_tool_has_a_repo() -> None:
    repos = status.release_repos()

    for command in (
        "rg",
        "fd",
        "bat",
        "lazygit",
        "starship",
        "herdr",
        "wezterm",
        "uv",
        "shellcheck",
    ):
        assert "/" in repos[command]


def _host_items(found: dict[str, str]):
    def path(_runner, command):
        return f"/home/dev/.local/bin/{command}" if command in found else None

    def version(_runner, command, _where):
        return found[command]

    return path, version


def test_status_prints_one_table_for_the_linux_host(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform_info = replace(_windows_platform(), os=OperatingSystem.LINUX, home=tmp_path)
    path, version = _host_items({
        "rg": "ripgrep 15.1.0",
        "fd": "fdfind 10.3.0",
        "python3": "Python 3.14.4",
    })

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_host_command_path", side_effect=path),
        mock.patch.object(cli, "_host_version", side_effect=version),
        mock.patch.object(cli.release_install, "STATE_DIR", tmp_path / "releases"),
    ):
        assert cli.print_status(runner, platform_info, FAKE) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "Linux: reading the installed tool versions..."
    assert lines[1].startswith("Linux: looking up the latest releases of ")
    assert lines[2] == "==> Linux"
    rows = {line.split()[0]: line.split() for line in lines[4:]}
    assert rows["rg"] == ["rg", "15.1.0", "15.1.0", "ok"]
    assert rows["fd"] == ["fd", "10.3.0", "10.4.0", "update"]
    assert rows["bat"] == ["bat", "-", "?", "missing"]
    assert rows["python3"] == ["python3", "3.14.4", "3.14", "ok"]


def test_status_reads_the_release_that_setup_recorded(tmp_path: Path) -> None:
    (tmp_path / "sd").write_text("1.1.0 1.0.0\n", encoding="utf-8")

    assert cli._release_state_version("sd", "sd 1.0.0", tmp_path) == "1.1.0"
    assert cli._release_state_version("sd", "sd 1.2.0", tmp_path) == "sd 1.2.0"


def test_status_on_a_windows_host_skips_wsl_when_the_side_is_windows(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    monkeypatch.setenv(cli.STATUS_SIDE_ENV, "windows")
    item = [status.Installed("rg", "C:/tools/rg.exe", "ripgrep 15.1.0")]

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_status_windows", return_value=item),
        mock.patch.object(cli, "_status_wsl", side_effect=AssertionError("WSL must not run")),
    ):
        cli.print_status(runner, _windows_platform(), FAKE)

    out = capsys.readouterr().out
    assert "==> Windows" in out
    assert "==> WSL" not in out


def test_only_status_is_a_mode() -> None:
    assert build_parser().parse_args(["--only", "status"]).only == "status"


def test_the_terminal_command_runs_the_installed_setup_release() -> None:
    for name in terminal_command.TERMINAL_COMMAND_TEMPLATES:
        text = terminal_command.render_terminal_command(name)
        assert "__" not in text.replace("__init__", "")
    assert terminal_command.setup_source().startswith(SETUP_ARCHIVES)
    assert (
        f'--from "{terminal_command.setup_source()}"'
        in terminal_command.render_terminal_command("terminal.ps1")
    )
    assert "\r\n" in terminal_command.render_terminal_command("terminal.cmd")


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="requires shellcheck")
def test_the_rendered_terminal_script_passes_shellcheck(tmp_path: Path) -> None:
    script = tmp_path / "terminal"
    script.write_text(terminal_command.render_terminal_command("terminal"), encoding="utf-8")

    result = subprocess.run(
        ["shellcheck", "-s", "bash", str(script)], check=False, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stdout


def _stub(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'#!/bin/sh\necho "{path.name} $*" >> "$TERMINAL_TEST_LOG"\n{body}\n', encoding="utf-8"
    )
    path.chmod(0o755)


needs_bash = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None, reason="runs the bash terminal script"
)


_FAKE_CURL = r"""for arg in "$@"; do url="$arg"; done
case "$url" in
  */releases/latest)
    [ -n "$TERMINAL_TEST_TAG" ] || exit 22
    base=https://github.com/niksavis/terminal/releases/tag
    printf 'HTTP/2 302\r\nlocation: %s/%s\r\n' "$base" "$TERMINAL_TEST_TAG" ;;
  */install.sh)
    printf '%s\n' 'echo "bootstrap ref=$TERMINAL_SETUP_REF" >> "$TERMINAL_TEST_LOG"' \
      'exit "$TERMINAL_TEST_BOOT"' ;;
  *) exit 22 ;;
esac"""


def _run_terminal(
    tmp_path: Path, *arguments: str, **extra: str
) -> subprocess.CompletedProcess[str]:
    if not (tmp_path / "stubs" / "curl").exists():
        _stub(tmp_path / "stubs" / "curl", _FAKE_CURL)
    if not (tmp_path / "stubs" / "uvx").exists():
        _stub(tmp_path / "stubs" / "uvx", "exit 0")
    script = tmp_path / "terminal"
    script.write_text(terminal_command.render_terminal_command("terminal"), encoding="utf-8")
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": guarded_system_path(tmp_path / "stubs"),
        "TERMINAL_TEST_LOG": str(tmp_path / "calls.log"),
        "TERMINAL_TEST_TAG": "",
        "TERMINAL_TEST_BOOT": "0",
        **extra,
    }
    return subprocess.run(
        ["bash", str(script), *arguments], check=False, capture_output=True, text=True, env=env
    )


@needs_bash
def test_terminal_status_runs_setup_status_then_agents_status(tmp_path: Path) -> None:
    _stub(tmp_path / "stubs" / "uvx", "echo tool-table")
    _stub(tmp_path / "home" / ".local" / "bin" / "agents", "echo agent-table")

    result = _run_terminal(tmp_path, "status", "--wsl")

    assert result.returncode == 0, result.stdout + result.stderr
    calls = (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()
    assert calls[0] == f"uvx --from {terminal_command.setup_source()} terminal-setup --only status"
    assert calls[1].startswith("agents status")
    assert result.stdout.index("tool-table") < result.stdout.index("agent-table")


@needs_bash
def test_terminal_status_without_agents_runs_only_setup(tmp_path: Path) -> None:
    _stub(tmp_path / "stubs" / "uvx", "echo tool-table")

    result = _run_terminal(tmp_path, "status", "--wsl")

    assert result.returncode == 0
    assert len((tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()) == 1


@needs_bash
@pytest.mark.parametrize(
    "arguments", [(), ("upgrade",), ("status", "--all"), ("status", "--pinned")]
)
def test_terminal_refuses_a_wrong_command_with_the_usage(
    tmp_path: Path, arguments: tuple[str, ...]
) -> None:
    (tmp_path / "stubs").mkdir()

    result = _run_terminal(tmp_path, *arguments)

    assert result.returncode == 2
    assert "usage: terminal <status|update> [--wsl|--win] [--pinned]" in result.stderr


@pytest.mark.skipif(shutil.which("pwsh") is None, reason="runs terminal.ps1 in pwsh")
def test_terminal_ps1_status_reads_only_the_windows_side(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    stubs = tmp_path / "stubs"
    ps1 = tmp_path / "terminal.ps1"
    ps1.write_text(terminal_command.render_terminal_command("terminal.ps1"), encoding="utf-8")
    if sys.platform == "win32":
        stubs.mkdir(parents=True)
        (stubs / "uvx.cmd").write_text(
            '@echo off\r\n>>"%TERMINAL_TEST_LOG%" echo uvx side=%TERMINAL_STATUS_SIDE% %*\r\n',
            encoding="utf-8",
        )
    else:
        _stub(stubs / "uvx", 'echo "side=$TERMINAL_STATUS_SIDE" >> "$TERMINAL_TEST_LOG"')
    pwsh = str(shutil.which("pwsh"))
    env = {
        **os.environ,
        "USERPROFILE": str(profile),
        "HOME": str(profile),
        "PATH": os.pathsep.join([str(stubs), str(Path(pwsh).parent)]),
        "TERMINAL_TEST_LOG": str(tmp_path / "calls.log"),
    }

    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-File", str(ps1), "status", "--win"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "side=windows" in (tmp_path / "calls.log").read_text(encoding="utf-8", errors="replace")


def test_setup_writes_the_terminal_command_on_linux(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform_info = replace(_windows_platform(), os=OperatingSystem.LINUX, home=tmp_path)

    with mock.patch.object(terminal_command, "is_running_in_wsl", return_value=False):
        terminal_command.deploy_terminal_command(runner, platform_info)

    target = tmp_path / ".local" / "bin" / "terminal"
    assert target.read_text(encoding="utf-8") == terminal_command.render_terminal_command(
        "terminal"
    )


def test_setup_refuses_another_terminal_command_by_name(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform_info = replace(_windows_platform(), os=OperatingSystem.LINUX, home=tmp_path)

    with (
        mock.patch.object(terminal_command, "is_running_in_wsl", return_value=False),
        mock.patch.object(runner, "which", return_value="/usr/bin/terminal"),
        pytest.raises(
            RuntimeError, match="another terminal command is on PATH at /usr/bin/terminal"
        ),
    ):
        terminal_command.deploy_terminal_command(runner, platform_info)

    assert not (tmp_path / ".local" / "bin" / "terminal").exists()


def test_setup_writes_the_windows_terminal_command_and_the_wsl_copy(tmp_path: Path) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    platform_info = replace(_windows_platform(), home=tmp_path)

    with (
        mock.patch.object(terminal_command, "is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._add_to_process_path"),
    ):
        terminal_command.deploy_terminal_command(runner, platform_info)

    bin_dir = tmp_path / ".local" / "bin"
    assert (bin_dir / "terminal.ps1").exists()
    assert (bin_dir / "terminal.cmd").read_bytes() == terminal_command.render_terminal_command(
        "terminal.cmd"
    ).encode()
    staged = tmp_path / ".local" / "share" / "terminal" / "terminal"
    assert any(str(staged) in command and command[-1] == "terminal" for command in runner.commands)


def test_apt_candidates_reads_each_package_candidate() -> None:
    policy = (
        "zsh:\n  Installed: 5.9-6ubuntu2\n  Candidate: 5.9-6ubuntu2\n"
        "git:\n  Installed: (none)\n  Candidate: 1:2.43.0-1ubuntu7.3\n"
        "tree:\n  Installed: (none)\n  Candidate: (none)\n"
    )

    assert status.apt_candidates(policy) == {
        "zsh": "5.9-6ubuntu2",
        "git": "1:2.43.0-1ubuntu7.3",
        "tree": "",
    }
    assert status.version_of("1:2.43.0-1ubuntu7.3") == "2.43.0"


def test_a_tool_without_releases_is_ok_when_present() -> None:
    items = [status.Installed("img-zoom", "/home/dev/.local/bin/img-zoom", "")]

    rows = status.rows(items, ["img-zoom"], {}, frozenset({"img-zoom"}))

    assert rows == [status.Row("img-zoom", "present", "-", "ok")]


def test_a_newer_dated_build_is_ok() -> None:
    item = status.Installed("wezterm", "/usr/bin/wezterm", "wezterm 20260707-093716-fff02ca5")

    assert status.state(item, "20240203-110809-5046fc22") == "ok"


def test_a_tool_without_a_version_and_a_dated_tag_is_unknown() -> None:
    item = status.Installed("wezterm", "/usr/bin/wezterm", "")

    assert status.state(item, "20240203-110809-5046fc22") == "unknown"


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("v0.23.0", "v0.23.0"),
        ("harness/terminal-status", "harness/terminal-status"),
        ("", None),
        ('main"; rm -rf ~', None),
        ("../evil", None),
    ],
)
def test_the_terminal_command_pins_the_ref_that_setup_ran_from(
    monkeypatch: pytest.MonkeyPatch, ref: str, expected: str | None
) -> None:
    monkeypatch.setenv("TERMINAL_SETUP_REF", ref)

    assert terminal_command.setup_ref() == (expected or f"v{terminal_command.__version__}")


def test_setup_refuses_another_terminal_command_in_wsl_by_name(tmp_path: Path) -> None:
    platform_info = replace(_windows_platform(), home=tmp_path)
    runner = RecordingRunner(
        reporter=CapturingReporter(),
        outputs={
            tuple(cli.wsl_exec_command("Ubuntu", ["sh", "-c", terminal_command._WSL_REFUSE])): (
                3,
                "/usr/local/bin/terminal\n",
            )
        },
    )

    with (
        mock.patch.object(terminal_command, "is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.prerequisites._add_to_process_path"),
        pytest.raises(
            RuntimeError, match="another terminal command is on PATH at /usr/local/bin/terminal"
        ),
    ):
        terminal_command.deploy_terminal_command(runner, platform_info)


_UVX_STATUS = (
    'plan="$TERMINAL_TEST_PLAN"; '
    'if [ -n "$TERMINAL_STATUS_QUIET" ] && [ -n "${TERMINAL_TEST_PLAN_AFTER+set}" ]; then '
    'plan="$TERMINAL_TEST_PLAN_AFTER"; fi; '
    'if [ -n "$TERMINAL_STATUS_PLAN" ]; then printf "%b" "$plan" > "$TERMINAL_STATUS_PLAN"; fi'
)
_AGENTS_UPDATE = (
    'echo "agents $*" >> "$TERMINAL_TEST_LOG"; '
    'printf "%b" "$TERMINAL_TEST_AGENTS" >> "$AGENTS_REPORT"; exit "$TERMINAL_TEST_AGENTS_EXIT"'
)
_ALL_OK_AGENTS = "ok claude\nok codex\nok daemon\nok copilot\n"


def _update(tmp_path: Path, *arguments: str, **extra: str) -> subprocess.CompletedProcess[str]:
    _stub(tmp_path / "stubs" / "uvx", _UVX_STATUS)
    _stub(tmp_path / "home" / ".local" / "bin" / "agents", _AGENTS_UPDATE)
    values = {
        "TERMINAL_TEST_TAG": terminal_command.setup_ref(),
        "TERMINAL_TEST_PLAN": "checked WSL 28\n",
        "TERMINAL_TEST_AGENTS": _ALL_OK_AGENTS,
        "TERMINAL_TEST_AGENTS_EXIT": "0",
        **extra,
    }
    return _run_terminal(tmp_path, "update", "--wsl", *arguments, **values)


def _summary(result: subprocess.CompletedProcess[str]) -> str:
    side, _, text = result.stdout.splitlines()[-1].partition(": ")
    assert side in {"WSL", "Linux", "macOS"}
    return text


def _bootstrap_calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return [line for line in lines if line.startswith("bootstrap")]


@needs_bash
def test_terminal_update_exits_1_and_names_a_failed_setup_run(tmp_path: Path) -> None:
    result = _update(tmp_path, TERMINAL_TEST_TAG="v9.9.9", TERMINAL_TEST_BOOT="3")

    assert result.returncode == 1
    assert "!! setup v9.9.9: failed" in result.stdout
    assert _summary(result).startswith("failed: setup v9.9.9")


@needs_bash
def test_terminal_update_exits_1_and_names_a_failed_agents_update(tmp_path: Path) -> None:
    result = _update(tmp_path, TERMINAL_TEST_AGENTS_EXIT="1")

    assert result.returncode == 1
    assert "!! agents update: failed" in result.stdout
    assert _summary(result) == "failed: agents update"


@needs_bash
def test_terminal_update_runs_no_updater_when_everything_is_up_to_date(tmp_path: Path) -> None:
    result = _update(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _bootstrap_calls(tmp_path) == []
    ref = terminal_command.setup_ref()
    assert _summary(result) == f"Everything is up to date (setup {ref}, 28 tools, 3 agents)"


@needs_bash
def test_terminal_update_runs_the_bootstrap_only_for_an_outdated_tool(tmp_path: Path) -> None:
    result = _update(
        tmp_path,
        TERMINAL_TEST_PLAN="checked WSL 28\noutdated WSL fd\n",
        TERMINAL_TEST_PLAN_AFTER="checked WSL 28\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ref = terminal_command.setup_ref()
    assert _bootstrap_calls(tmp_path) == [f"bootstrap ref={ref}"]
    assert "because of not up to date: fd" in result.stdout
    assert _summary(result) == "updated fd"


@needs_bash
def test_terminal_update_says_nothing_changed_when_setup_fixed_nothing(tmp_path: Path) -> None:
    result = _update(
        tmp_path,
        TERMINAL_TEST_PLAN="checked WSL 28\noutdated WSL fd\n",
        TERMINAL_TEST_PLAN_AFTER="checked WSL 28\noutdated WSL fd\n",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    ref = terminal_command.setup_ref()
    assert _summary(result) == f"setup {ref} ran; nothing changed (still not up to date: fd)"


@needs_bash
def test_terminal_update_names_a_new_setup_release_as_the_change(tmp_path: Path) -> None:
    result = _update(
        tmp_path, TERMINAL_TEST_TAG="v9.9.9", TERMINAL_TEST_PLAN_AFTER="checked WSL 28\n"
    )

    ref = terminal_command.setup_ref()
    assert _summary(result) == f"updated setup {ref} -> v9.9.9"


@needs_bash
def test_terminal_update_ends_with_a_summary_when_the_release_lookup_fails(tmp_path: Path) -> None:
    result = _update(tmp_path, TERMINAL_TEST_TAG="")

    assert result.returncode == 1
    assert _summary(result) == "failed: release lookup"


@needs_bash
def test_terminal_update_ends_with_a_summary_when_the_status_check_fails(tmp_path: Path) -> None:
    _stub(tmp_path / "stubs" / "uvx", "exit 4")
    _stub(tmp_path / "home" / ".local" / "bin" / "agents", _AGENTS_UPDATE)
    values = {"TERMINAL_TEST_TAG": terminal_command.setup_ref(), "TERMINAL_TEST_AGENTS_EXIT": "0"}

    result = _run_terminal(tmp_path, "update", "--wsl", **values)

    assert result.returncode == 1
    assert _summary(result) == "failed: status check"


@needs_bash
def test_terminal_update_runs_the_bootstrap_for_a_new_setup_release(tmp_path: Path) -> None:
    result = _update(tmp_path, TERMINAL_TEST_TAG="v9.9.9")

    assert result.returncode == 0, result.stdout + result.stderr
    assert _bootstrap_calls(tmp_path) == ["bootstrap ref=v9.9.9"]
    log = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert f"{terminal_command.RELEASES}/download/v9.9.9/install.sh" in log


@needs_bash
def test_terminal_update_names_only_the_agent_that_was_updated(tmp_path: Path) -> None:
    agents_report = "ok claude\nupdated codex\nupdated daemon\nok copilot\n"

    result = _update(tmp_path, TERMINAL_TEST_AGENTS=agents_report)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _bootstrap_calls(tmp_path) == []
    assert _summary(result) == "updated codex codex daemon"


@needs_bash
def test_terminal_update_pinned_keeps_the_installed_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TERMINAL_SETUP_REF", "v0.1.0")

    result = _update(
        tmp_path, "--pinned", TERMINAL_TEST_TAG="v9.9.9", TERMINAL_TEST_PLAN="outdated WSL fd\n"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "target v0.1.0" in result.stdout
    assert _bootstrap_calls(tmp_path) == ["bootstrap ref=v0.1.0"]


@needs_bash
@pytest.mark.parametrize("tag", ["", "v1.2", "v1.2.3;rm", "latest"])
def test_terminal_update_stops_when_the_latest_release_cannot_be_read(
    tmp_path: Path, tag: str
) -> None:
    result = _update(tmp_path, TERMINAL_TEST_TAG=tag)

    assert result.returncode == 1
    assert "could not be read" in result.stdout
    assert "terminal update --pinned" in result.stdout
    assert _bootstrap_calls(tmp_path) == []


@needs_bash
def test_terminal_update_shows_a_line_before_each_slow_step(tmp_path: Path) -> None:
    _stub(tmp_path / "stubs" / "uvx", "sleep 1; " + _UVX_STATUS)
    _stub(tmp_path / "home" / ".local" / "bin" / "agents", "sleep 1; " + _AGENTS_UPDATE)
    script = tmp_path / "terminal"
    script.write_text(terminal_command.render_terminal_command("terminal"), encoding="utf-8")
    if not (tmp_path / "stubs" / "curl").exists():
        _stub(tmp_path / "stubs" / "curl", _FAKE_CURL)
    env = {
        "HOME": str(tmp_path / "home"),
        "PATH": guarded_system_path(tmp_path / "stubs"),
        "TERMINAL_TEST_LOG": str(tmp_path / "calls.log"),
        "TERMINAL_TEST_TAG": terminal_command.setup_ref(),
        "TERMINAL_TEST_BOOT": "0",
        "TERMINAL_TEST_PLAN": "checked WSL 28\n",
        "TERMINAL_TEST_AGENTS": _ALL_OK_AGENTS,
        "TERMINAL_TEST_AGENTS_EXIT": "0",
    }
    process = subprocess.Popen(
        ["bash", str(script), "update", "--wsl"], stdout=subprocess.PIPE, text=True, env=env
    )
    assert process.stdout is not None
    started = time.monotonic()
    stamps = [(time.monotonic() - started, line.rstrip()) for line in process.stdout]
    process.wait()

    assert process.returncode == 0
    names = [line for _, line in stamps]
    done = {
        line.split(": done (")[0]: index for index, line in enumerate(names) if ": done (" in line
    }
    assert names.index("==> status check") < done["status check"]
    assert names.index("==> agents update") < done["agents update"]
    gaps = [later[0] - earlier[0] for earlier, later in itertools.pairwise(stamps)]
    assert stamps[0][0] < 1.0
    assert max(gaps) < 2.0


@pytest.mark.parametrize(
    ("output", "lag"),
    [
        ("codex-cli 0.171.0\n0.170.0-x86_64-unknown-linux-musl\n", ("0.171.0", "0.170.0")),
        ("codex-cli 0.171.0\n0.171.0-x86_64-unknown-linux-musl\n", None),
        ("codex-cli 0.171.0\n", None),
        ("", None),
    ],
)
def test_setup_names_agents_update_for_an_older_codex_daemon(
    output: str, lag: tuple[str, str] | None
) -> None:
    assert agents._daemon_lag(output) == lag


def test_setup_ends_with_the_terminal_status_hint() -> None:
    source = Path(cli.__file__).read_text(encoding="utf-8")

    assert "terminal status" in source
    assert "Verify anytime with" not in source


_PS_UPDATE_WRAPPER = r"""
function Invoke-WebRequest {
  if (-not $env:TERMINAL_TEST_TAG) { throw "offline" }
  $base = "https://github.com/niksavis/terminal/releases/tag"
  [pscustomobject]@{ Headers = @{ Location = "$base/$env:TERMINAL_TEST_TAG" } }
}
function Invoke-RestMethod {
  $url = "$args"
  $log = 'Add-Content -Path $env:TERMINAL_TEST_LOG -Value '
  $log += '("bootstrap ref=" + $env:TERMINAL_SETUP_REF'
  $first = $log + ' + " url=' + $url + '")'
  $lines = @($first, "Write-Output 'bootstrap says hello'")
  if ($env:TERMINAL_TEST_BOOT -ne "0") { $lines += "throw 'bootstrap broke'" }
  return ($lines -join "; ")
}
$script = $args[0]
$rest = @($args | Select-Object -Skip 1)
& $script @rest
exit $LASTEXITCODE
"""
_PS_AGENTS = r"""
Add-Content -Path $env:TERMINAL_TEST_LOG -Value "agents $args"
Write-Output "agents table line"
$lines = $env:TERMINAL_TEST_AGENTS -split ','
if ($env:AGENTS_REPORT) { Add-Content -Path $env:AGENTS_REPORT -Value $lines }
exit [int]$env:TERMINAL_TEST_AGENTS_EXIT
"""


def _ps_stub_uvx(stubs: Path) -> None:
    stubs.mkdir(parents=True, exist_ok=True)
    posix = stubs / "uvx"
    posix.write_text(
        '#!/bin/sh\necho "status table line"\nplan="$TERMINAL_TEST_PLAN"\n'
        'if [ -n "$TERMINAL_STATUS_QUIET" ] && [ -n "${TERMINAL_TEST_PLAN_AFTER+set}" ]; then '
        'plan="$TERMINAL_TEST_PLAN_AFTER"; fi\n'
        'if [ -n "$TERMINAL_STATUS_PLAN" ]; then '
        'printf "%b" "$plan" > "$TERMINAL_STATUS_PLAN"; fi\n',
        encoding="utf-8",
    )
    posix.chmod(0o755)
    (stubs / "uvx.cmd").write_text(
        "@echo off\r\necho status table line\r\nif defined TERMINAL_STATUS_PLAN "
        'powershell -NoProfile -Command "$p = $env:TERMINAL_TEST_PLAN; '
        "if ($env:TERMINAL_STATUS_QUIET -and (Test-Path Env:TERMINAL_TEST_PLAN_AFTER)) "
        "{ $p = $env:TERMINAL_TEST_PLAN_AFTER }; "
        "[IO.File]::WriteAllText($env:TERMINAL_STATUS_PLAN, $p.Replace('|', [char]10))\"\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )


def _run_ps_update(tmp_path: Path, **extra: str) -> subprocess.CompletedProcess[str]:
    profile = tmp_path / "profile"
    agents_ps1 = profile / ".local" / "bin" / "agents.ps1"
    agents_ps1.parent.mkdir(parents=True, exist_ok=True)
    agents_ps1.write_text(_PS_AGENTS, encoding="utf-8")
    stubs = tmp_path / "stubs"
    _ps_stub_uvx(stubs)
    script = tmp_path / "terminal.ps1"
    script.write_text(terminal_command.render_terminal_command("terminal.ps1"), encoding="utf-8")
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(_PS_UPDATE_WRAPPER, encoding="utf-8")
    pwsh = str(shutil.which("pwsh"))
    system = [str(Path(pwsh).parent)]
    if sys.platform == "win32":
        system.append(str(Path(os.environ.get("SYSTEMROOT", "C:/Windows")) / "System32"))
        system.append(
            str(
                Path(os.environ.get("SYSTEMROOT", "C:/Windows"))
                / "System32"
                / "WindowsPowerShell"
                / "v1.0"
            )
        )
    else:
        system += ["/usr/bin", "/bin"]
    plan = extra.pop("plan", "checked Windows 19\n")
    env = {
        **os.environ,
        "USERPROFILE": str(profile),
        "HOME": str(profile),
        "PATH": os.pathsep.join([str(stubs), *system]),
        "TERMINAL_TEST_LOG": str(tmp_path / "calls.log"),
        "TERMINAL_TEST_TAG": terminal_command.setup_ref(),
        "TERMINAL_TEST_BOOT": "0",
        "TERMINAL_TEST_PLAN": plan.replace("\n", "|") if sys.platform == "win32" else plan,
        "TERMINAL_TEST_AGENTS": "ok claude,ok codex,ok daemon,ok copilot",
        "TERMINAL_TEST_AGENTS_EXIT": "0",
        **extra,
    }
    return subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(wrapper),
            str(script),
            "update",
            "--win",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _ps_bootstraps(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines() if log.exists() else []
    return [line for line in lines if line.startswith("bootstrap")]


needs_pwsh = pytest.mark.skipif(shutil.which("pwsh") is None, reason="runs terminal.ps1 in pwsh")


@needs_pwsh
def test_terminal_ps1_update_exits_1_and_names_a_failed_setup_run(tmp_path: Path) -> None:
    result = _run_ps_update(tmp_path, TERMINAL_TEST_TAG="v9.9.9", TERMINAL_TEST_BOOT="1")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "!! setup v9.9.9: failed" in result.stdout
    assert "Windows: failed: setup v9.9.9" in result.stdout


@needs_pwsh
def test_terminal_ps1_update_exits_1_and_names_a_failed_agents_update(tmp_path: Path) -> None:
    result = _run_ps_update(tmp_path, TERMINAL_TEST_AGENTS_EXIT="1")

    assert result.returncode == 1, result.stdout + result.stderr
    assert "!! agents update: failed" in result.stdout


@needs_pwsh
def test_terminal_ps1_update_runs_no_updater_when_everything_is_up_to_date(tmp_path: Path) -> None:
    result = _run_ps_update(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _ps_bootstraps(tmp_path) == []
    ref = terminal_command.setup_ref()
    assert f"Windows: Everything is up to date (setup {ref}, 19 tools, 3 agents)" in result.stdout


@needs_pwsh
def test_terminal_ps1_update_streams_the_bootstrap_and_agents_output(tmp_path: Path) -> None:
    result = _run_ps_update(tmp_path, plan="checked Windows 19\noutdated Windows sd\n")

    assert result.returncode == 0, result.stdout + result.stderr
    ref = terminal_command.setup_ref()
    assert _ps_bootstraps(tmp_path)[0].startswith(f"bootstrap ref={ref}")
    assert f"/download/{ref}/install.ps1" in _ps_bootstraps(tmp_path)[0]
    assert "status table line" in result.stdout
    assert "bootstrap says hello" in result.stdout
    assert "agents table line" in result.stdout
    assert "ran; nothing changed (still not up to date: sd)" in result.stdout
    assert "terminal update: done (Windows)" in result.stdout


@needs_pwsh
@pytest.mark.parametrize("tag", ["", "v1.2.3;rm"])
def test_terminal_ps1_update_stops_when_the_latest_release_cannot_be_read(
    tmp_path: Path, tag: str
) -> None:
    result = _run_ps_update(tmp_path, TERMINAL_TEST_TAG=tag)

    assert result.returncode == 1
    assert "terminal update --pinned" in result.stdout
    assert _ps_bootstraps(tmp_path) == []


def _plan_row(command: str, state: str) -> status.Row:
    return status.Row(command, "1.0.0", "1.0.0", state)


def test_the_update_plan_names_only_what_setup_can_update() -> None:
    table_rows = [
        _plan_row("rg", "ok"),
        _plan_row("fd", "update"),
        _plan_row("bat", "missing"),
        _plan_row("herdr", "missing"),
        _plan_row("zsh", "update"),
        _plan_row("starship", status.MANAGED),
        _plan_row("shellcheck", "unknown"),
    ]

    assert status.plan_lines("WSL", table_rows) == [
        "checked WSL 7",
        "outdated WSL fd",
        "outdated WSL bat",
        "apt WSL zsh",
    ]


def test_a_machine_wide_copy_shows_managed_instead_of_update() -> None:
    path = "C:/Program Files/starship/bin/starship.exe"
    items = [status.Installed("starship", path, "1.26.0", managed=True)]

    table_rows = status.rows(items, ["starship"], {"starship": "v1.27.0"})

    assert table_rows[0].state == status.MANAGED


def test_windows_status_reads_the_recorded_release_and_the_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    releases = tmp_path / "terminal-setup" / "releases"
    releases.mkdir(parents=True)
    (releases / "sd.exe").write_text("1.1.0 1.0.0\n", encoding="utf-8")
    info = {
        "sd": ("C:/Users/u/.local/bin/sd.exe", "sd 1.0.0", "user profile"),
        "starship": (
            "C:/Program Files/starship/bin/starship.exe",
            "starship 1.26.0",
            "machine-wide",
        ),
    }

    with (
        mock.patch.object(
            cli, "_windows_tool_info", side_effect=lambda _r, _p, command: info.get(command)
        ),
        mock.patch.object(cli.release_install, "STATE_DIR", tmp_path / "shell-releases"),
    ):
        found = cli._status_windows(runner, _windows_platform())
    items = {item.command: item for item in found if item}

    assert items["sd"].version == "1.1.0"
    assert not items["sd"].managed
    assert items["starship"].managed
    assert status.rows([items["sd"]], ["sd"], {"sd": "v1.1.0"})[0].state == "ok"


def test_a_tool_printing_another_version_than_its_tag_stays_ok_in_wsl(tmp_path: Path) -> None:
    (tmp_path / "sd").write_text("1.1.0 1.0.0\n", encoding="utf-8")
    version = cli._release_state_version("sd", "sd 1.0.0", tmp_path)
    item = status.Installed("sd", "/home/u/.local/bin/sd", version)

    assert status.rows([item], ["sd"], {"sd": "v1.1.0"})[0].state == "ok"


def test_status_writes_the_update_plan_when_asked(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    plan = tmp_path / "plan"
    monkeypatch.setenv(cli.STATUS_PLAN_ENV, str(plan))
    monkeypatch.setenv(cli.STATUS_SIDE_ENV, "windows")
    item = [status.Installed("rg", "C:/tools/rg.exe", "ripgrep 14.0.0")]

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_status_windows", return_value=item),
    ):
        cli.print_status(runner, _windows_platform(), FAKE)

    capsys.readouterr()
    lines = plan.read_text(encoding="utf-8").splitlines()
    assert lines == ["checked Windows 1", "outdated Windows rg"]


def test_quiet_status_writes_only_the_plan(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    plan = tmp_path / "plan"
    monkeypatch.setenv(cli.STATUS_PLAN_ENV, str(plan))
    monkeypatch.setenv(cli.STATUS_QUIET_ENV, "1")
    monkeypatch.setenv(cli.STATUS_SIDE_ENV, "windows")
    item = [status.Installed("rg", "C:/tools/rg.exe", "ripgrep 14.0.0")]

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_status_windows", return_value=item),
    ):
        cli.print_status(runner, _windows_platform(), FAKE)

    assert capsys.readouterr().out == ""
    assert plan.read_text(encoding="utf-8").splitlines() == [
        "checked Windows 1",
        "outdated Windows rg",
    ]


@needs_pwsh
def test_terminal_ps1_update_names_the_tool_that_setup_fixed(tmp_path: Path) -> None:
    after = "checked Windows 19\n"
    result = _run_ps_update(
        tmp_path,
        plan="checked Windows 19\noutdated Windows sd\n",
        TERMINAL_TEST_PLAN_AFTER=after.replace("\n", "|") if sys.platform == "win32" else after,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Windows: updated sd" in result.stdout


def test_a_nightly_wezterm_build_names_its_source_instead_of_an_older_stable_tag() -> None:
    item = status.Installed("wezterm", "/usr/bin/wezterm", "wezterm 20260707-093716-fff02ca5")

    row = status.rows([item], ["wezterm"], {"wezterm": "20240203-110809-5046fc22"})[0]

    assert (row.installed, row.latest, row.state) == ("20260707-093716-fff02ca5", "nightly", "ok")


def test_a_stable_wezterm_build_shows_the_latest_stable_tag() -> None:
    item = status.Installed("wezterm", "/usr/bin/wezterm", "wezterm 20240203-110809-5046fc22")

    row = status.rows([item], ["wezterm"], {"wezterm": "20240203-110809-5046fc22"})[0]

    assert (row.latest, row.state) == ("20240203-110809-5046fc22", "ok")


@needs_bash
def test_an_unknown_argument_names_a_newer_release_and_its_install_command(tmp_path: Path) -> None:
    result = _run_terminal(tmp_path, "upgrade", TERMINAL_TEST_TAG="v99.0.0")

    assert result.returncode == 2
    assert "terminal v99.0.0 is available" in result.stderr
    assert (
        f"curl -LsSf {terminal_command.RELEASES}/download/v99.0.0/install.sh | sh" in result.stderr
    )


@needs_bash
@pytest.mark.parametrize("tag", ["", "v0.0.1", "latest"])
def test_an_unknown_argument_names_no_release_when_none_is_newer(tmp_path: Path, tag: str) -> None:
    result = _run_terminal(tmp_path, "upgrade", TERMINAL_TEST_TAG=tag)

    assert result.returncode == 2
    assert "is available" not in result.stderr


@needs_pwsh
def test_terminal_ps1_unknown_argument_names_a_newer_release(tmp_path: Path) -> None:
    script = tmp_path / "terminal.ps1"
    script.write_text(terminal_command.render_terminal_command("terminal.ps1"), encoding="utf-8")
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(_PS_UPDATE_WRAPPER, encoding="utf-8")
    pwsh = str(shutil.which("pwsh"))
    env = {**os.environ, "TERMINAL_TEST_TAG": "v99.0.0", "TERMINAL_TEST_LOG": str(tmp_path / "log")}

    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-File", str(wrapper), str(script), "upgrade"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 2
    assert "terminal v99.0.0 is available" in result.stdout
    assert "/download/v99.0.0/install.ps1 | iex" in result.stdout


def test_terminal_update_status_shows_only_rows_that_need_action(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    monkeypatch.setenv(cli.STATUS_SIDE_ENV, "windows")
    monkeypatch.setenv(cli.STATUS_CHANGES_ONLY_ENV, "1")
    items = [
        status.Installed("rg", "C:/tools/rg.exe", "ripgrep 15.1.0"),
        status.Installed("fd", "C:/tools/fd.exe", "fd 10.3.0"),
    ]

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_status_windows", return_value=items),
    ):
        cli.print_status(runner, _windows_platform(), FAKE)

    out = capsys.readouterr().out
    assert "fd " in out
    assert "rg " not in out


def test_terminal_update_status_prints_no_table_when_every_row_is_ok(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = RecordingRunner(reporter=CapturingReporter())
    monkeypatch.setenv(cli.STATUS_SIDE_ENV, "windows")
    monkeypatch.setenv(cli.STATUS_CHANGES_ONLY_ENV, "1")
    items = [status.Installed("rg", "C:/tools/rg.exe", "ripgrep 15.1.0")]

    with (
        mock.patch.object(cli, "is_running_in_wsl", return_value=False),
        mock.patch.object(cli, "_status_windows", return_value=items),
    ):
        cli.print_status(runner, _windows_platform(), FAKE)

    assert "==> " not in capsys.readouterr().out
