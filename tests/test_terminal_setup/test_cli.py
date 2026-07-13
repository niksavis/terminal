"""Tests for the CLI entry point."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from terminal_setup.cli import build_parser, main, run_setup
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo


def test_parser_dry_run_flag() -> None:
    """The parser must accept --dry-run."""
    parser = build_parser()
    args = parser.parse_args(["--dry-run"])
    assert args.dry_run is True


def test_parser_check_flag() -> None:
    """The parser must accept --check."""
    parser = build_parser()
    args = parser.parse_args(["--check"])
    assert args.check is True


def test_parser_skip_flags() -> None:
    """The parser must accept skip flags."""
    parser = build_parser()
    args = parser.parse_args(["--skip-vscode", "--skip-starship"])
    assert args.skip_vscode is True
    assert args.skip_starship is True


def test_parser_report_flag() -> None:
    """The parser must accept --report."""
    parser = build_parser()
    args = parser.parse_args(["--report"])
    assert args.report is True


def test_parser_report_only_flag() -> None:
    """The parser must accept --report-only."""
    parser = build_parser()
    args = parser.parse_args(["--report-only"])
    assert args.report_only is True


def test_parser_uninstall_system_versions_flag() -> None:
    """The parser must accept --uninstall-system-versions."""
    parser = build_parser()
    args = parser.parse_args(["--uninstall-system-versions"])
    assert args.uninstall_system_versions is True


def test_parser_keep_system_versions_flag() -> None:
    """The parser must accept --keep-system-versions."""
    parser = build_parser()
    args = parser.parse_args(["--keep-system-versions"])
    assert args.keep_system_versions is True


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
    """Main with --check must return 0 or 1 without side effects."""
    with mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False):
        result = main(["--check", "--dry-run"])
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


def test_main_rejects_conflicting_system_version_flags() -> None:
    """Main must exit with an error when both system-version flags are given."""
    with mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False):
        result = main([
            "--check",
            "--dry-run",
            "--uninstall-system-versions",
            "--keep-system-versions",
        ])
    assert result == 2


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
        user_install=True,
    )
    with (
        mock.patch("terminal_setup.cli.is_running_in_wsl", return_value=False),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_tools") as mock_tools,
        mock.patch("terminal_setup.cli.prerequisites.ensure_wsl_cli_extras"),
        mock.patch("terminal_setup.cli.prerequisites.ensure_wezterm"),
        mock.patch("terminal_setup.cli.configs.deploy_all"),
    ):
        result = run_setup(
            fake_platform,
            mock.Mock(),
            skip_vscode=True,
            skip_starship=True,
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


def test_main_report_only_skips_setup_actions() -> None:
    """Report-only mode must avoid setup and only print verification output."""
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
        result = main(["--report-only"])

    assert result == 0
    mock_check.assert_called_once()
    mock_report.assert_called_once()
    mock_setup.assert_not_called()
