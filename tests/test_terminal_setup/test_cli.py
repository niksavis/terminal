from __future__ import annotations

import io
import os
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup import progress
from terminal_setup.cli import build_parser, main, run_setup
from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    PlatformInfo,
    path_without_own_environment,
    windows_powershell_module_path,
)
from terminal_setup.runner import Runner


@pytest.fixture(autouse=True)
def _main_path_change_stays_in_the_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))


def test_own_environment_is_dropped_from_path() -> None:
    sep = os.pathsep
    path = sep.join(["/env/bin", "/home/dev/.local/bin", "/env/bin/", "/usr/bin"])

    kept = path_without_own_environment(path, "/env/bin/python", in_virtualenv=True)

    assert kept == sep.join(["/home/dev/.local/bin", "/usr/bin"])


def test_path_is_kept_outside_a_virtualenv() -> None:
    assert path_without_own_environment("/usr/bin", "/usr/bin/python3", in_virtualenv=False) == (
        "/usr/bin"
    )


def test_main_drops_its_own_environment_from_path(monkeypatch: pytest.MonkeyPatch) -> None:
    own = str(Path(sys.executable).parent)
    monkeypatch.setenv("PATH", os.pathsep.join([own, "/usr/bin"]))
    monkeypatch.setattr(sys, "prefix", "/env")
    monkeypatch.setattr(sys, "base_prefix", "/base")

    with mock.patch("terminal_setup.cli._dispatch", return_value=0):
        main([])

    assert own not in os.environ["PATH"].split(os.pathsep)


PS7_AND_51 = ";".join([
    r"C:\Users\dev\Documents\PowerShell\Modules",
    r"C:\Program Files\PowerShell\Modules",
    r"c:\program files\powershell\7\Modules",
    r"C:\Program Files\WindowsPowerShell\Modules",
    r"C:\WINDOWS\system32\WindowsPowerShell\v1.0\Modules",
    r"D:\team\modules",
])
WINDOWS_POWERSHELL_ONLY = ";".join([
    r"C:\Program Files\WindowsPowerShell\Modules",
    r"C:\WINDOWS\system32\WindowsPowerShell\v1.0\Modules",
    r"D:\team\modules",
])


def test_powershell_7_module_directories_are_dropped_and_the_rest_kept() -> None:
    assert windows_powershell_module_path(PS7_AND_51) == WINDOWS_POWERSHELL_ONLY


@pytest.mark.parametrize(
    ("host", "expected"), [("win32", WINDOWS_POWERSHELL_ONLY), ("linux", PS7_AND_51)]
)
def test_main_filters_the_module_path_only_on_windows(
    monkeypatch: pytest.MonkeyPatch, host: str, expected: str
) -> None:
    monkeypatch.setenv("PSMODULEPATH", PS7_AND_51)
    monkeypatch.setattr(sys, "platform", host)

    with mock.patch("terminal_setup.cli._dispatch", return_value=0):
        main([])

    assert os.environ["PSMODULEPATH"] == expected


def test_parser_dry_run_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parser_only_choices() -> None:
    parser = build_parser()
    for phase in ("config", "report", "status"):
        args = parser.parse_args(["--only", phase])
        assert args.only == phase
    assert parser.parse_args([]).only is None


def test_parser_only_rejects_invalid_phase() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--only", "bogus"])


def test_parser_skip_flags() -> None:
    parser = build_parser()
    args = parser.parse_args(["--skip-vscode", "--skip-starship", "--skip-claude"])
    assert args.skip_vscode is True
    assert args.skip_starship is True
    assert args.skip_claude is True


def test_parser_no_nerd_font_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--no-nerd-font"])
    assert args.no_nerd_font is True


@pytest.mark.parametrize(
    ("arguments", "kept"),
    [
        (["--report"], "terminal-setup --only report"),
        (["--user-install"], "run: terminal-setup"),
        (["--only", "check"], "terminal-setup --only report"),
    ],
)
def test_a_removed_option_is_refused_by_name_with_the_kept_command(
    arguments: list[str], kept: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        build_parser().parse_args(arguments)

    assert stopped.value.code == 2
    error = capsys.readouterr().err
    assert f"{' '.join(arguments)} was removed" in error
    assert kept in error


def test_parser_system_versions_choice() -> None:
    parser = build_parser()
    assert parser.parse_args(["--system-versions", "keep"]).system_versions == "keep"
    assert parser.parse_args(["--system-versions", "uninstall"]).system_versions == "uninstall"
    assert parser.parse_args([]).system_versions is None
    with pytest.raises(SystemExit):
        parser.parse_args(["--system-versions", "both"])


def test_parser_optional_terminal_cwd_flags() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "--windows-terminal-cwd",
        "D:\\Workspace",
        "--wsl-terminal-cwd",
        "$HOME/workspace",
    ])
    assert args.windows_terminal_cwd == "D:\\Workspace"
    assert args.wsl_terminal_cwd == "$HOME/workspace"


def test_main_report_mode_runs_the_prerequisite_check() -> None:
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.run_check", return_value=0) as check,
        mock.patch("terminal_setup.cli.print_setup_report"),
    ):
        result = main(["--only", "report", "--dry-run"])
    assert result == 0
    check.assert_called_once()


def test_main_runs_wsl_setup_when_inside_wsl() -> None:
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.cli.prerequisites.herdr_installed", return_value=False),
        mock.patch("terminal_setup.cli.platform.detect_platform") as mock_detect,
        mock.patch("terminal_setup.cli.run_check", return_value=0),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
    ):
        mock_detect.return_value = PlatformInfo(
            os=OperatingSystem.LINUX,
            package_manager=PackageManager.APT,
            is_wsl_available=True,
            is_wsl_default_debian_family=True,
            wsl_distribution="Ubuntu",
            shell="/bin/zsh",
            home=Path.home(),
            wezterm_config_dir=Path.home() / ".config" / "wezterm",
            vscode_settings_path=None,
        )
        result = main(["--dry-run"])
    assert result == 0
    mock_tools.assert_called_once()


def test_main_config_only_skips_prereq_check() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_debian_family=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.platform.detect_platform", return_value=fake_platform),
        mock.patch("terminal_setup.cli.run_check") as mock_check,
        mock.patch("terminal_setup.cli.run_setup", return_value=0) as mock_setup,
    ):
        result = main(["--only", "config"])

    assert result == 0
    mock_check.assert_not_called()
    assert mock_setup.call_args.kwargs["config_only"] is True


def test_run_setup_config_only_skips_package_installs() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=True,
        is_wsl_default_debian_family=True,
        wsl_distribution="Ubuntu",
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras") as mock_extras,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm") as mock_wezterm,
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node") as mock_node,
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship") as mock_starship,
        mock.patch("terminal_setup.cli.configs.deploy_all") as mock_deploy,
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=False,
            skip_claude=False,
            no_nerd_font=False,
            config_only=True,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )

    assert result == 0
    mock_tools.assert_not_called()
    mock_extras.assert_not_called()
    mock_wezterm.assert_not_called()
    mock_node.assert_not_called()
    mock_starship.assert_not_called()
    mock_deploy.assert_called_once()


def test_run_setup_on_a_windows_host_uses_no_sudo_for_wsl_tools() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_debian_family=True,
        wsl_distribution="Ubuntu",
        shell="powershell",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm") as mock_wezterm,
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl"),
        mock.patch(
            "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship", return_value=False
        ),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native"),
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )

    assert result == 0
    assert mock_tools.call_args.kwargs["no_sudo"] is True
    assert mock_wezterm.call_args.kwargs["no_sudo"] is True


@pytest.mark.parametrize("update", [False, True])
def test_a_plain_run_updates_owned_tools_and_only_update_upgrades_the_distro(
    update: bool,
) -> None:
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages") as mock_system,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm") as mock_wezterm,
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship") as mock_starship,
        mock.patch(
            "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship", return_value=False
        ) as mock_batch,
        mock.patch("terminal_setup.cli.configs.deploy_all"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native"),
    ):
        result = run_setup(
            _windows_platform(),
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=False,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
            update=update,
        )

    assert result == 0
    assert mock_wezterm.call_args.kwargs["update"] is True
    assert not mock_starship.called
    assert mock_batch.call_args.kwargs == {"install_herdr": False, "starship": True}
    assert mock_system.call_args.kwargs["upgrade"] is update


def test_run_setup_ends_with_the_command_that_starts_wezterm_on_windows() -> None:
    runner = mock.Mock(failures=[])
    location = "C:\\Users\\test\\AppData\\Local\\Programs\\WezTerm\\wezterm-gui.exe"
    with (
        mock.patch("terminal_setup.prerequisites.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.wezterm_location", return_value=location),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
    ):
        result = run_setup(
            _windows_platform(),
            runner,
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=True,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )

    assert result == 0
    steps = [call.args[0] for call in runner.reporter.step.call_args_list]
    assert any(step.endswith(f"& '{location}'") for step in steps)


@pytest.mark.parametrize("herdr", [False, True])
def test_run_setup_installs_herdr_only_when_asked(herdr: bool) -> None:
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_herdr") as mock_herdr,
        mock.patch(
            "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship", return_value=herdr
        ) as mock_batch,
        mock.patch("terminal_setup.cli.agents.ensure_herdr_integrations") as mock_integrations,
        mock.patch("terminal_setup.cli.prerequisites.herdr_installed", return_value=False),
        mock.patch("terminal_setup.cli.configs.deploy_all") as mock_deploy,
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native"),
    ):
        result = run_setup(
            _windows_platform(),
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            no_sudo=False,
            herdr=herdr,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
            selected_agents=("claude",),
        )

    assert result == 0
    assert not mock_herdr.called
    assert mock_batch.call_args.kwargs == {"install_herdr": herdr, "starship": False}
    assert mock_integrations.called is herdr
    if herdr:
        assert mock_integrations.call_args.args[2] == ("claude",)
    assert mock_deploy.call_args.kwargs["herdr"] is herdr


def _plain_windows_run(**patches: object) -> dict[str, mock.Mock]:
    names = {
        "ensure_herdr": "terminal_setup.cli.prerequisites.ensure_herdr",
        "batch": "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship",
        "integrations": "terminal_setup.cli.agents.ensure_herdr_integrations",
        "deploy_agents": "terminal_setup.cli.agents.deploy_agents_command",
    }
    fixed = [
        "terminal_setup.cli.prerequisites.ensure_wsl_tools",
        "terminal_setup.cli.prerequisites.ensure_wsl_system_packages",
        "terminal_setup.cli.prerequisites.ensure_wsl_cli_extras",
        "terminal_setup.cli.prerequisites.ensure_wezterm",
        "terminal_setup.cli.windows_tools.ensure_windows_tools",
        "terminal_setup.cli.prerequisites.ensure_python",
        "terminal_setup.cli.prerequisites.ensure_uv_windows",
        "terminal_setup.cli.agents.ensure_agents",
        "terminal_setup.cli.prerequisites.ensure_node",
        "terminal_setup.cli.prerequisites.ensure_starship",
        "terminal_setup.cli.configs.deploy_all",
        "terminal_setup.cli.configs.install_img_zoom_wsl",
        "terminal_setup.cli.configs.install_img_zoom_native",
        "terminal_setup.cli.terminal_command.deploy_terminal_command",
    ]
    with ExitStack() as stack:
        stack.enter_context(mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False))
        for target in fixed:
            stack.enter_context(mock.patch(target))
        for target, value in patches.items():
            stack.enter_context(mock.patch(target, return_value=value))
        mocks = {key: stack.enter_context(mock.patch(path)) for key, path in names.items()}
        mocks["batch"].return_value = patches.get(
            "terminal_setup.cli.prerequisites.herdr_installed", False
        )
        run_setup(
            _windows_platform(),
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )
    return mocks


def test_a_plain_run_updates_an_installed_herdr_without_the_option() -> None:
    mocks = _plain_windows_run(**{
        "terminal_setup.cli.prerequisites.herdr_installed": True,
        "terminal_setup.cli.agents.installed_agents": (),
    })

    assert not mocks["ensure_herdr"].called
    assert mocks["batch"].call_args.kwargs == {"install_herdr": False, "starship": False}
    assert not mocks["integrations"].called


def test_a_plain_run_deploys_the_agents_command_when_an_agent_is_installed() -> None:
    mocks = _plain_windows_run(**{
        "terminal_setup.cli.prerequisites.herdr_installed": False,
        "terminal_setup.cli.agents.installed_agents": ("codex",),
    })

    assert mocks["deploy_agents"].called
    assert not mocks["ensure_herdr"].called
    assert mocks["batch"].called


def test_a_plain_run_without_agents_or_herdr_installs_neither() -> None:
    mocks = _plain_windows_run(**{
        "terminal_setup.cli.prerequisites.herdr_installed": False,
        "terminal_setup.cli.agents.installed_agents": (),
    })

    assert not mocks["deploy_agents"].called
    assert not mocks["ensure_herdr"].called


def _windows_platform() -> PlatformInfo:
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_debian_family=True,
        wsl_distribution="Ubuntu",
        shell="powershell",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )


def _run_setup_install_mode(
    fake_platform: PlatformInfo, *, system_install: bool, no_sudo: bool
) -> tuple[mock.Mock, mock.Mock, mock.Mock, mock.Mock]:
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_shell_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_host_cli_extras") as mock_extras,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl") as mock_zoom_wsl,
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native") as mock_zoom_native,
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
        mock.patch("terminal_setup.cli.configs.install_vscode_wsl_extension"),
        mock.patch(
            "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship", return_value=False
        ),
        mock.patch("terminal_setup.cli.configs.configure_vscode_terminal"),
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(failures=[]),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=system_install,
            no_sudo=no_sudo,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )
    assert result == 0
    return mock_tools, mock_extras, mock_zoom_wsl, mock_zoom_native


def test_parser_system_install_flag() -> None:
    parser = build_parser()
    assert parser.parse_args(["--system-install"]).system_install is True
    assert parser.parse_args([]).system_install is False


def test_run_setup_default_is_user_local_on_windows() -> None:
    mock_tools, *_ = _run_setup_install_mode(
        _windows_platform(), system_install=False, no_sudo=False
    )
    assert mock_tools.call_args.kwargs["no_sudo"] is True


def test_run_setup_system_install_uses_sudo_on_windows() -> None:
    mock_tools, *_ = _run_setup_install_mode(
        _windows_platform(), system_install=True, no_sudo=False
    )
    assert mock_tools.call_args.kwargs["no_sudo"] is False


def test_run_setup_native_linux_default_uses_package_manager() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_debian_family=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    _, mock_extras, *_ = _run_setup_install_mode(fake_platform, system_install=False, no_sudo=False)
    assert mock_extras.call_args.kwargs["no_sudo"] is False


def test_main_report_mode_skips_setup_actions() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_debian_family=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.platform.detect_platform", return_value=fake_platform),
        mock.patch("terminal_setup.cli.run_check", return_value=0) as mock_check,
        mock.patch("terminal_setup.cli.print_setup_report") as mock_report,
        mock.patch("terminal_setup.cli.run_setup") as mock_setup,
    ):
        result = main(["--only", "report"])

    assert result == 0
    mock_check.assert_called_once()
    mock_report.assert_called_once()
    mock_setup.assert_not_called()


def test_main_surfaces_child_stderr_on_failure() -> None:
    error = subprocess.CalledProcessError(
        returncode=2, cmd=["wsl", "cp"], output="", stderr="cp: permission denied"
    )
    with (
        mock.patch("terminal_setup.cli._dispatch", side_effect=error),
        mock.patch("sys.stderr"),
        mock.patch("sys.stdout"),
    ):
        status = main([])
    assert status == 1


def test_main_reports_clean_error_for_value_errors() -> None:
    with (
        mock.patch("terminal_setup.cli._dispatch", side_effect=ValueError("bad value")),
        mock.patch("sys.stderr"),
        mock.patch("sys.stdout"),
    ):
        status = main([])
    assert status == 1


def test_run_setup_on_windows_installs_img_zoom_in_wsl_and_natively() -> None:
    _, _, zoom_wsl, zoom_native = _run_setup_install_mode(
        _windows_platform(), system_install=False, no_sudo=False
    )
    zoom_wsl.assert_called_once()
    zoom_native.assert_called_once()


def test_run_setup_on_linux_installs_img_zoom_natively_only() -> None:
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_debian_family=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    _, _, zoom_wsl, zoom_native = _run_setup_install_mode(
        fake_platform, system_install=False, no_sudo=False
    )
    zoom_wsl.assert_not_called()
    zoom_native.assert_called_once()


@pytest.mark.parametrize(("changed", "runs"), [(False, False), (True, True)])
def test_setup_skips_the_run_checks_when_nothing_changed(
    tmp_path: Path, changed: bool, runs: bool
) -> None:
    reporter = progress.PhasedReporter(progress.PlainDisplay(io.StringIO()), tmp_path / "log", 6)
    reporter.phase("Tools", "Windows")
    if changed:
        reporter.info("installed sd 1.1.0 into C:/x/sd.exe")
    runner = Runner(reporter=reporter)
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_system_packages"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.windows_tools.ensure_windows_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_python"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_uv_windows"),
        mock.patch("terminal_setup.cli.agents.ensure_agents"),
        mock.patch("terminal_setup.cli.agents.report_daemon_lag"),
        mock.patch("terminal_setup.cli.agents.installed_agents", return_value=()),
        mock.patch("terminal_setup.cli.terminal_command.deploy_terminal_command"),
        mock.patch("terminal_setup.cli.prerequisites.herdr_installed", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.prerequisites.wezterm_location", return_value=None),
        mock.patch(
            "terminal_setup.cli.prerequisites.ensure_wsl_herdr_and_starship", return_value=False
        ),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_wsl"),
        mock.patch("terminal_setup.cli.configs.install_img_zoom_native"),
        mock.patch("terminal_setup.cli.verify_tools_run") as checks,
    ):
        run_setup(
            _windows_platform(),
            runner,
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )

    assert checks.called is runs
