"""Command-line interface for the terminal setup."""

from __future__ import annotations

import argparse
import sys

from . import configs, platform, prerequisites
from .runner import ConsoleReporter, Runner


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="terminal-setup",
        description="Install and configure a cross-platform terminal environment.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the steps that would be executed without making changes.",
    )
    parser.add_argument(
        "--skip-vscode",
        action="store_true",
        help="Skip VS Code settings and extension configuration.",
    )
    parser.add_argument(
        "--skip-starship",
        action="store_true",
        help="Skip starship prompt installation and configuration.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check prerequisites and exit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print additional diagnostic output.",
    )
    parser.add_argument(
        "--user-install",
        action="store_true",
        help="Install tools into user-writable locations without admin rights (Windows only).",
    )
    return parser


def run_check(platform_info: platform.PlatformInfo, runner: Runner) -> int:
    """Check prerequisites and report status."""
    statuses = prerequisites.check_all(platform_info, runner)
    all_present = True
    for status in statuses:
        if status.present:
            runner.reporter.info(f"[OK] {status.name}: {status.message}")
        else:
            all_present = False
            runner.reporter.warn(f"[MISSING] {status.name}: {status.message}")
    if not all_present:
        runner.reporter.error("Some prerequisites are missing.")
        return 1
    runner.reporter.info("All prerequisites are satisfied.")
    return 0


def run_setup(
    platform_info: platform.PlatformInfo,
    runner: Runner,
    *,
    skip_vscode: bool,
    skip_starship: bool,
    user_install: bool,
) -> int:
    """Run the full setup workflow."""
    runner.reporter.info(f"Detected platform: {platform_info.os.name}")
    runner.reporter.info(f"Package manager: {platform_info.package_manager.name.lower()}")
    if user_install:
        runner.reporter.info("User-install mode: tools will be installed without admin rights")

    if platform_info.os == platform.OperatingSystem.WINDOWS:
        if not platform_info.is_wsl_available:
            runner.reporter.warn("WSL is not available; attempting to install Ubuntu.")
            prerequisites.install_wsl_ubuntu(runner)
        elif not platform_info.is_wsl_default_ubuntu:
            runner.reporter.warn("WSL default is not Ubuntu; attempting to install Ubuntu.")
            prerequisites.install_wsl_ubuntu(runner)
        prerequisites.ensure_wsl_tools(runner, platform_info)
        prerequisites.ensure_wsl_cli_extras(runner, platform_info)
    else:
        prerequisites.ensure_shell_tools(runner, platform_info)
        prerequisites.ensure_host_cli_extras(runner, platform_info)

    prerequisites.ensure_wezterm(runner, platform_info, user_install=user_install)

    if not skip_starship:
        prerequisites.ensure_starship(runner, platform_info, user_install=user_install)

    configs.deploy_all(runner, platform_info, include_starship=not skip_starship)

    if not skip_vscode:
        configs.install_vscode_wsl_extension(runner, platform_info)
        configs.configure_vscode_terminal(runner, platform_info)

    runner.reporter.info("Setup complete.")
    if user_install and platform_info.os == platform.OperatingSystem.WINDOWS:
        runner.reporter.info("Restart your terminal for the updated PATH to take effect.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = ConsoleReporter()
    runner = Runner(dry_run=args.dry_run, reporter=reporter)
    platform_info = platform.detect_platform(user_install=args.user_install)

    if args.check:
        return run_check(platform_info, runner)

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
        user_install=args.user_install,
    )


if __name__ == "__main__":
    sys.exit(main())
