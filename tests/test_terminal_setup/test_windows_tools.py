from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest

from terminal_setup import release_install, windows_tools
from terminal_setup.cli import build_parser
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo
from terminal_setup.prerequisites import remove_from_user_path
from terminal_setup.runner import Runner
from terminal_setup.windows_tools import (
    STARSHIP,
    WINDOWS_TOOLS,
    Origin,
    classify,
    ensure_tool,
    ensure_windows_tools,
    winget_id,
    winget_package_dir,
)

HOME = "C:/Users/test"
PACKAGES = f"{HOME}/AppData/Local/Microsoft/WinGet/Packages"
RG = WINDOWS_TOOLS[0]


def make_platform() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_debian_family=True,
        wsl_distribution="Ubuntu",
        shell="powershell",
        home=Path(HOME),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )


class Reporter:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __getattr__(self, kind: str):
        return lambda message, *_rest: self.messages.append((kind, str(message)))


class FakeRunner:
    def __init__(self, *, unattended: bool = False, answer: bool = False) -> None:
        self.dry_run = False
        self.unattended = unattended
        self.answer = answer
        self.failures: list[str] = []
        self.commands: list[list[str]] = []
        self.prompts: list[str] = []
        self.reporter = Reporter()

    def run(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    def confirm(self, prompt: str) -> bool:
        self.prompts.append(prompt)
        return self.answer

    def ensure_dir(self, _path: Path) -> None:
        return None


@pytest.mark.parametrize(
    ("path", "origin"),
    [
        (None, Origin.MISSING),
        (f"{HOME}/AppData/Local/Programs/terminal-tools/bin/rg.exe", Origin.OURS),
        ("C:/Program Files/ripgrep/rg.exe", Origin.MACHINE),
        (
            f"{PACKAGES}/BurntSushi.ripgrep.MSVC_Microsoft.Winget.Source_8wekyb3d8bbwe/"
            "ripgrep-15.1.0-x86_64-pc-windows-msvc/rg.exe",
            Origin.WINGET,
        ),
        (f"{HOME}/scoop/shims/rg.exe", Origin.OTHER),
    ],
)
def test_classify_names_where_a_copy_came_from(path: str | None, origin: Origin) -> None:
    assert classify(path, make_platform(), RG) is origin


@pytest.mark.parametrize("folder", ["starship", "starship/bin"])
def test_the_old_setup_starship_folder_is_legacy(folder: str) -> None:
    path = f"{HOME}/AppData/Local/Programs/{folder}/starship.exe"

    assert classify(path, make_platform(), STARSHIP) is Origin.LEGACY
    assert classify(path.replace("starship.exe", "rg.exe"), make_platform(), RG) is Origin.OTHER


def test_the_winget_id_comes_from_the_package_folder() -> None:
    path = f"{PACKAGES}/sharkdp.fd_Microsoft.Winget.Source_8wekyb3d8bbwe/fd-v10/fd.exe"

    package = winget_package_dir(path)

    assert package == PureWindowsPath(
        f"{PACKAGES}/sharkdp.fd_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    assert package is not None
    assert winget_id(package) == "sharkdp.fd"


class Calls:
    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        found: str | None,
        *,
        verify_ok: bool = True,
        hidden: tuple[str, ...] = (),
    ):
        self.events: list[str] = []
        copies = ([found] if found else []) + list(hidden)
        monkeypatch.setattr(windows_tools, "all_copies", lambda _c, _p: copies)

        def install(_runner, platform, tool, *, update):
            self.events.append(f"install {tool.command} update={update}")
            return platform.terminal_tools_dir / f"{tool.command}.exe"

        def verify(_runner, executable):
            self.events.append(f"verify {Path(executable).name}")
            if not verify_ok:
                raise RuntimeError("--version failed")

        monkeypatch.setattr(windows_tools, "_install", install)
        monkeypatch.setattr(windows_tools, "_verify", verify)
        monkeypatch.setattr(
            windows_tools,
            "_uninstall_winget",
            lambda _r, _p, package: self.events.append(f"uninstall {winget_id(package)}"),
        )
        monkeypatch.setattr(
            windows_tools,
            "_retire_legacy",
            lambda _r, _p, tool: self.events.append(f"retire {tool.command}"),
        )


WINGET_RG = f"{PACKAGES}/BurntSushi.ripgrep.MSVC_Microsoft.Winget.Source_8wekyb3d8bbwe/rg.exe"


@pytest.mark.parametrize("update", [False, True])
def test_a_missing_or_own_tool_installs_into_terminal_tools(
    monkeypatch: pytest.MonkeyPatch, update: bool
) -> None:
    calls = Calls(monkeypatch, None)

    ensure_tool(cast(Runner, FakeRunner()), make_platform(), RG, update=update, policy=None)

    assert calls.events == [f"install rg update={update}"]


@pytest.mark.parametrize(("policy", "unattended"), [(None, True), ("keep", False), ("keep", True)])
def test_a_winget_copy_is_kept_without_replace(
    monkeypatch: pytest.MonkeyPatch, policy: str | None, unattended: bool
) -> None:
    calls = Calls(monkeypatch, WINGET_RG)
    runner = FakeRunner(unattended=unattended)

    ensure_tool(cast(Runner, runner), make_platform(), RG, update=False, policy=policy)

    assert calls.events == []
    assert runner.prompts == []
    assert any("--winget-versions replace" in message for _, message in runner.reporter.messages)


def test_replace_installs_and_checks_ours_before_it_uninstalls_winget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch, WINGET_RG)

    ensure_tool(
        cast(Runner, FakeRunner(unattended=True)),
        make_platform(),
        RG,
        update=False,
        policy="replace",
    )

    assert calls.events == [
        "install rg update=False",
        "verify rg.exe",
        "uninstall BurntSushi.ripgrep.MSVC",
    ]


def test_a_failed_check_keeps_the_winget_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, WINGET_RG, verify_ok=False)

    with pytest.raises(RuntimeError, match="--version failed"):
        ensure_tool(cast(Runner, FakeRunner()), make_platform(), RG, update=False, policy="replace")

    assert "uninstall BurntSushi.ripgrep.MSVC" not in calls.events


@pytest.mark.parametrize(("answer", "replaced"), [(True, True), (False, False)])
def test_an_interactive_run_asks_per_tool(
    monkeypatch: pytest.MonkeyPatch, answer: bool, replaced: bool
) -> None:
    calls = Calls(monkeypatch, WINGET_RG)
    runner = FakeRunner(answer=answer)

    ensure_tool(cast(Runner, runner), make_platform(), RG, update=False, policy=None)

    assert len(runner.prompts) == 1
    assert "BurntSushi.ripgrep.MSVC" in runner.prompts[0]
    assert ("uninstall BurntSushi.ripgrep.MSVC" in calls.events) is replaced


@pytest.mark.parametrize(
    ("found", "reason"),
    [("C:/Program Files/ripgrep/rg.exe", "administrator"), (f"{HOME}/scoop/rg.exe", "not from")],
)
def test_a_machine_wide_or_foreign_copy_is_kept_even_with_replace(
    monkeypatch: pytest.MonkeyPatch, found: str, reason: str
) -> None:
    calls = Calls(monkeypatch, found)
    runner = FakeRunner()

    ensure_tool(cast(Runner, runner), make_platform(), RG, update=True, policy="replace")

    assert calls.events == []
    assert any(reason in message for _, message in runner.reporter.messages)


WINGET_STARSHIP = f"{PACKAGES}/Starship.Starship_Microsoft.Winget.Source_8wekyb3d8bbwe/starship.exe"
MACHINE_STARSHIP = "C:/Program Files/starship/bin/starship.exe"


def test_replace_removes_a_hidden_winget_copy_and_installs_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch, MACHINE_STARSHIP, hidden=(WINGET_STARSHIP,))

    ensure_tool(
        cast(Runner, FakeRunner(unattended=True)),
        make_platform(),
        STARSHIP,
        update=False,
        policy="replace",
    )

    assert calls.events == ["uninstall Starship.Starship"]


@pytest.mark.parametrize(("policy", "answer"), [("keep", False), (None, False)])
def test_a_hidden_winget_copy_is_kept_without_replace(
    monkeypatch: pytest.MonkeyPatch, policy: str | None, answer: bool
) -> None:
    calls = Calls(monkeypatch, MACHINE_STARSHIP, hidden=(WINGET_STARSHIP,))
    runner = FakeRunner(answer=answer)

    ensure_tool(cast(Runner, runner), make_platform(), STARSHIP, update=False, policy=policy)

    assert calls.events == []
    assert any(
        "unused winget copy" in message and "--winget-versions replace" in message
        for _, message in runner.reporter.messages
    )


def test_an_interactive_run_asks_about_a_hidden_winget_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch, MACHINE_STARSHIP, hidden=(WINGET_STARSHIP,))
    runner = FakeRunner(answer=True)

    ensure_tool(cast(Runner, runner), make_platform(), STARSHIP, update=False, policy=None)

    assert len(runner.prompts) == 1
    assert "never runs" in runner.prompts[0]
    assert calls.events == ["uninstall Starship.Starship"]


def test_a_hidden_copy_that_did_not_come_from_winget_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = Calls(monkeypatch, MACHINE_STARSHIP, hidden=(f"{HOME}/scoop/shims/starship.exe",))

    ensure_tool(
        cast(Runner, FakeRunner()), make_platform(), STARSHIP, update=False, policy="replace"
    )

    assert calls.events == []


def test_all_copies_lists_each_copy_once_in_path_order_without_ours(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, second, ours = tmp_path / "first", tmp_path / "second", tmp_path / "ours"
    name = "demo.exe" if sys.platform == "win32" else "demo"
    for folder in (first, second, ours):
        folder.mkdir()
        tool = folder / name
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)
    platform = make_platform()
    monkeypatch.setattr(type(platform), "terminal_tools_dir", property(lambda _self: ours))
    monkeypatch.setenv("PATH", os.pathsep.join([str(ours), str(first), str(first), str(second)]))

    copies = windows_tools.all_copies("demo", platform)

    assert [Path(copy) for copy in copies] == [(first / name).resolve(), (second / name).resolve()]


def test_the_old_starship_moves_into_terminal_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = Calls(monkeypatch, f"{HOME}/AppData/Local/Programs/starship/starship.exe")

    ensure_tool(cast(Runner, FakeRunner()), make_platform(), STARSHIP, update=False, policy=None)

    assert calls.events == [
        "install starship update=False",
        "verify starship.exe",
        "retire starship",
    ]


def test_a_winget_uninstall_stays_in_user_scope_and_drops_only_gone_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    platform = make_platform()
    package = PureWindowsPath(f"{PACKAGES}/sharkdp.fd_Microsoft.Winget.Source_8wekyb3d8bbwe")
    entries = [str(package / "fd-v10"), "%USERPROFILE%\\.local\\bin", str(tmp_path)]
    removed: list[list[str]] = []
    monkeypatch.setattr(windows_tools, "read_user_path_entries", lambda _r: entries)
    monkeypatch.setattr(
        windows_tools, "remove_from_user_path", lambda _r, stale, _b: removed.append(stale)
    )
    runner = FakeRunner()

    windows_tools._uninstall_winget(cast(Runner, runner), platform, package)

    command = runner.commands[0]
    assert command[:5] == ["winget", "uninstall", "--id", "sharkdp.fd", "--exact"]
    assert command[command.index("--scope") + 1] == "user"
    assert removed == [[str(package / "fd-v10")]]


def test_the_path_removal_backs_up_before_it_writes(tmp_path: Path) -> None:
    runner = FakeRunner()

    remove_from_user_path(cast(Runner, runner), ["C:\\gone\\"], tmp_path / "backup.txt")

    script = runner.commands[0][-1]
    assert script.index("Set-Content") < script.index("SetValue")
    assert "'C:\\gone'" in script
    assert "-ieq" in script


def test_the_path_removal_writes_nothing_when_nothing_is_stale() -> None:
    runner = FakeRunner()

    remove_from_user_path(cast(Runner, runner), [], Path("unused"))

    assert runner.commands == []


@pytest.mark.parametrize("include_starship", [True, False])
def test_ensure_windows_tools_covers_every_tool_and_starship_on_request(
    monkeypatch: pytest.MonkeyPatch, include_starship: bool
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        windows_tools, "ensure_tool", lambda _r, _p, tool, **_k: seen.append(tool.command)
    )
    monkeypatch.setattr(windows_tools, "replace_winget_wezterm", lambda *_a, **_k: None)
    monkeypatch.setattr(windows_tools, "_add_to_user_path", lambda *_a: None)

    ensure_windows_tools(
        cast(Runner, FakeRunner()),
        make_platform(),
        update=False,
        policy=None,
        include_starship=include_starship,
    )

    expected = [tool.command for tool in WINDOWS_TOOLS] + (["starship"] if include_starship else [])
    assert seen == expected


MEASURED_ASSETS = {
    "rg": "ripgrep-15.2.0-{a}-pc-windows-msvc.zip",
    "fd": "fd-v10.5.0-{a}-pc-windows-msvc.zip",
    "bat": "bat-v0.26.1-{a}-pc-windows-msvc.zip",
    "jq": "jq-windows-{w}.exe",
    "yq": "yq_windows_{w}.exe",
    "ast-grep": "app-{a}-pc-windows-msvc.zip",
    "sd": "sd-v1.1.0-x86_64-pc-windows-msvc.zip",
    "delta": "delta-0.20.1-x86_64-pc-windows-msvc.zip",
    "typos": "typos-v1.51.1-{a}-pc-windows-msvc.zip",
    "just": "just-1.58.0-{a}-pc-windows-msvc.zip",
    "xh": "xh-v0.26.2-x86_64-pc-windows-msvc.zip",
    "shellcheck": "shellcheck-v0.11.0.zip",
    "fzf": "fzf-0.74.5-windows_{w}.zip",
    "lazygit": "lazygit_0.66.1_windows_{l}.zip",
    "starship": "starship-{a}-pc-windows-msvc.zip",
}


@pytest.mark.parametrize("tool", [*WINDOWS_TOOLS, STARSHIP], ids=lambda tool: tool.command)
@pytest.mark.parametrize(
    ("machine", "arch"),
    [("AMD64", ("x86_64", "amd64", "x86_64")), ("ARM64", ("aarch64", "arm64", "arm64"))],
)
def test_each_tool_selects_its_windows_asset(
    tool: windows_tools.WindowsTool, machine: str, arch: tuple[str, str, str]
) -> None:
    template = MEASURED_ASSETS[tool.command]
    names = {
        template.format(a=arch[0], w=arch[1], l=arch[2]),
        template.format(a="x86_64", w="amd64", l="x86_64"),
        f"{tool.command}-linux-x86_64.tar.gz",
        template.format(a=arch[0], w=arch[1], l=arch[2]) + ".sha256",
    }
    assets = [{"name": name} for name in sorted(names)]

    selected = release_install.select_asset(assets, list(tool.patterns), machine)

    assert selected["name"] == template.format(a=arch[0], w=arch[1], l=arch[2])


def test_the_command_line_accepts_only_keep_or_replace() -> None:
    parser = build_parser()

    assert parser.parse_args(["--winget-versions", "replace"]).winget_versions == "replace"
    assert parser.parse_args([]).winget_versions is None
    with pytest.raises(SystemExit):
        parser.parse_args(["--winget-versions", "remove"])
