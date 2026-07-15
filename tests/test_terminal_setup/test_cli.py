"""Tests for the CLI entry point."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest import mock

import pytest

from terminal_setup.cli import build_parser, main, run_setup
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo


def test_parser_dry_run_flag() -> None:
    """The parser must accept --dry-run."""
    parser = build_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parser_only_choices() -> None:
    """--only must accept the check/config/report phases."""
    parser = build_parser()
    for phase in ("check", "config", "report"):
        args = parser.parse_args(["--only", phase])
        assert args.only == phase
    assert parser.parse_args([]).only is None


def test_parser_only_rejects_invalid_phase() -> None:
    """--only must reject an unknown phase."""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--only", "bogus"])


def test_parser_skip_flags() -> None:
    """The parser must accept skip flags."""
    parser = build_parser()
    args = parser.parse_args(["--skip-vscode", "--skip-starship", "--skip-claude"])
    assert args.skip_vscode is True
    assert args.skip_starship is True
    assert args.skip_claude is True


def test_parser_no_nerd_font_flag() -> None:
    """The parser must accept --no-nerd-font."""
    parser = build_parser()
    args = parser.parse_args(["--no-nerd-font"])
    assert args.no_nerd_font is True


def test_parser_report_flag() -> None:
    """The parser must accept --report."""
    parser = build_parser()
    args = parser.parse_args(["--report"])
    assert args.report is True


def test_parser_system_versions_choice() -> None:
    """--system-versions must accept keep/uninstall and reject anything else."""
    parser = build_parser()
    assert parser.parse_args(["--system-versions", "keep"]).system_versions == "keep"
    assert parser.parse_args(["--system-versions", "uninstall"]).system_versions == "uninstall"
    assert parser.parse_args([]).system_versions is None
    with pytest.raises(SystemExit):
        parser.parse_args(["--system-versions", "both"])


def test_parser_optional_terminal_cwd_flags() -> None:
    """The parser must accept optional user-specific terminal cwd values."""
    parser = build_parser()
    args = parser.parse_args([
        "--windows-terminal-cwd",
        "D:\\Workspace",
        "--wsl-terminal-cwd",
        "$HOME/workspace",
    ])
    assert args.windows_terminal_cwd == "D:\\Workspace"
    assert args.wsl_terminal_cwd == "$HOME/workspace"


def test_main_check_mode() -> None:
    """--only check must return 0 or 1 without side effects."""
    with mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False):
        result = main(["--only", "check", "--dry-run"])
    assert result in (0, 1)


def test_main_runs_wsl_setup_when_inside_wsl() -> None:
    """Main should run the WSL setup path when executed from inside WSL."""
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.cli.platform.detect_platform") as mock_detect,
        mock.patch("terminal_setup.cli.run_check", return_value=0),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
    ):
        mock_detect.return_value = PlatformInfo(
            os=OperatingSystem.LINUX,
            package_manager=PackageManager.APT,
            is_wsl_available=True,
            is_wsl_default_ubuntu=True,
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
    """--only config must skip the prerequisite check and run setup in config-only mode."""
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
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
    """config-only must deploy configs without installing or checking packages."""
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=True,
        is_wsl_default_ubuntu=True,
        wsl_distribution="Ubuntu",
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=True),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras") as mock_extras,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm") as mock_wezterm,
        mock.patch("terminal_setup.cli.prerequisites.ensure_node") as mock_node,
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship") as mock_starship,
        mock.patch("terminal_setup.cli.configs.deploy_all") as mock_deploy,
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(),
            skip_vscode=True,
            skip_starship=False,
            skip_claude=False,
            no_nerd_font=False,
            config_only=True,
            system_install=False,
            user_install=False,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            report=False,
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


def test_run_setup_user_install_implies_no_sudo_for_wsl_tools() -> None:
    """--user-install must install WSL tools without sudo even without --no-sudo."""
    fake_platform = PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_ubuntu=True,
        wsl_distribution="Ubuntu",
        shell="powershell",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm") as mock_wezterm,
        mock.patch("terminal_setup.cli.configs.deploy_all"),
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=False,
            user_install=True,
            no_sudo=False,
            uninstall_system_versions=False,
            keep_system_versions=False,
            report=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )

    assert result == 0
    assert mock_tools.call_args.kwargs["no_sudo"] is True
    assert mock_wezterm.call_args.kwargs["no_sudo"] is True


def _windows_platform() -> PlatformInfo:
    """Build a Windows PlatformInfo for install-mode tests."""
    return PlatformInfo(
        os=OperatingSystem.WINDOWS,
        package_manager=PackageManager.WINGET,
        is_wsl_available=True,
        is_wsl_default_ubuntu=True,
        wsl_distribution="Ubuntu",
        shell="powershell",
        home=Path.home(),
        wezterm_config_dir=None,
        vscode_settings_path=None,
    )


def _run_setup_install_mode(
    fake_platform: PlatformInfo, *, system_install: bool, user_install: bool, no_sudo: bool
) -> tuple[mock.Mock, mock.Mock]:
    """Run setup with only install flags varied; return (wsl_tools, host_extras) mocks."""
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_shell_tools"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_host_cli_extras") as mock_extras,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_node"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_starship"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
        mock.patch("terminal_setup.cli.configs.install_vscode_wsl_extension"),
        mock.patch("terminal_setup.cli.configs.configure_vscode_terminal"),
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(),
            skip_vscode=True,
            skip_starship=True,
            skip_claude=True,
            no_nerd_font=False,
            config_only=False,
            system_install=system_install,
            user_install=user_install,
            no_sudo=no_sudo,
            uninstall_system_versions=False,
            keep_system_versions=False,
            report=False,
            windows_terminal_cwd=None,
            wsl_terminal_cwd=None,
        )
    assert result == 0
    return mock_tools, mock_extras


def test_parser_system_install_flag() -> None:
    """The parser must accept --system-install."""
    parser = build_parser()
    assert parser.parse_args(["--system-install"]).system_install is True
    assert parser.parse_args([]).system_install is False


def test_run_setup_default_is_user_local_on_windows() -> None:
    """With no flags on Windows, WSL tools must install user-locally (no sudo)."""
    mock_tools, _ = _run_setup_install_mode(
        _windows_platform(), system_install=False, user_install=False, no_sudo=False
    )
    assert mock_tools.call_args.kwargs["no_sudo"] is True


def test_run_setup_system_install_uses_sudo_on_windows() -> None:
    """--system-install must take the sudo/system-wide path even on Windows."""
    mock_tools, _ = _run_setup_install_mode(
        _windows_platform(), system_install=True, user_install=False, no_sudo=False
    )
    assert mock_tools.call_args.kwargs["no_sudo"] is False


def test_run_setup_native_linux_default_uses_package_manager() -> None:
    """With no flags on a native Linux host, host extras must use the package manager (sudo)."""
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution=None,
        shell="/bin/zsh",
        home=Path.home(),
        wezterm_config_dir=Path.home() / ".config" / "wezterm",
        vscode_settings_path=None,
    )
    _, mock_extras = _run_setup_install_mode(
        fake_platform, system_install=False, user_install=False, no_sudo=False
    )
    assert mock_extras.call_args.kwargs["no_sudo"] is False


def test_main_report_mode_skips_setup_actions() -> None:
    """--only report must avoid setup and only print verification output."""
    fake_platform = PlatformInfo(
        os=OperatingSystem.LINUX,
        package_manager=PackageManager.APT,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
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
    """A failed subprocess must print its captured stderr, not a traceback."""
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
    """Validation errors (e.g. --wsl-terminal-cwd) exit 1 without a traceback."""
    with (
        mock.patch("terminal_setup.cli._dispatch", side_effect=ValueError("bad value")),
        mock.patch("sys.stderr"),
        mock.patch("sys.stdout"),
    ):
        status = main([])
    assert status == 1
