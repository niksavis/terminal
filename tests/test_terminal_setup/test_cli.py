"""Tests for the CLI entry point."""

from __future__ import annotations

from terminal_setup.cli import build_parser, main


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
    result = main(["--check", "--dry-run"])
    assert result in (0, 1)
