"""Command-line interface for the terminal setup."""

from __future__ import annotations

import argparse
import sys

from . import configs, platform, prerequisites
from .platform import is_running_in_wsl, wsl_exec_command
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
        "--user-install",
        action="store_true",
        help=(
            "Install tools into user-writable locations without admin rights. "
            "Tools inside WSL/Linux are installed without sudo (as with --no-sudo)."
        ),
    )
    parser.add_argument(
        "--no-sudo",
        action="store_true",
        dest="no_sudo",
        help=(
            "Avoid sudo/password prompts by installing tools into user-writable "
            "locations where possible. Base system packages that are missing will "
            "be skipped with a warning."
        ),
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print a post-setup verification report for tools and deployed configs.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only print the verification report; do not run setup actions.",
    )
    parser.add_argument(
        "--uninstall-system-versions",
        action="store_true",
        dest="uninstall_system_versions",
        help=(
            "When a system-wide version of a tool exists and a user-local copy is "
            "installed, automatically remove the system version without prompting."
        ),
    )
    parser.add_argument(
        "--keep-system-versions",
        action="store_true",
        dest="keep_system_versions",
        help=("Keep system-wide versions of tools and only warn; do not prompt to uninstall them."),
    )
    parser.add_argument(
        "--windows-terminal-cwd",
        help=("Optional Windows terminal cwd for VS Code (user-specific). Example: D:\\Workspace"),
    )
    parser.add_argument(
        "--wsl-terminal-cwd",
        help=(
            "Optional WSL startup cwd for terminal profiles and WezTerm config "
            "(user-specific). Example: $HOME/workspace"
        ),
    )
    return parser


def _report_status(runner: Runner, label: str, ok: bool, detail: str = "") -> None:
    """Print a single report status line."""
    suffix = f" ({detail})" if detail else ""
    if ok:
        runner.reporter.info(f"[REPORT][OK] {label}{suffix}")
        return
    runner.reporter.warn(f"[REPORT][MISSING] {label}{suffix}")


def _wsl_command_present(
    runner: Runner, platform_info: platform.PlatformInfo, command: str
) -> tuple[bool, str]:
    """Return whether a command exists inside the configured WSL distro.

    Prefer the user-local copy in ~/.local/bin so that tools whose binary name
    conflicts with a system utility (e.g. ast-grep's ``sg`` vs util-linux's
    ``sg``) are reported accurately.
    """
    script = (
        f"if test -x ~/.local/bin/{command}; then echo ~/.local/bin/{command}; "
        f"else command -v {command} || true; fi"
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
    output = result.stdout.strip()
    return bool(output), output


def _wsl_file_exists(
    runner: Runner, platform_info: platform.PlatformInfo, path: str
) -> tuple[bool, str]:
    """Return whether a file exists inside the configured WSL distro."""
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
    """Report Windows host tools and WezTerm config status."""
    for command in ["wezterm", "starship"]:
        if command == "starship" and not include_starship:
            continue
        path = runner.which(command)
        _report_status(runner, f"windows:{command}", path is not None, path or "")

    if platform_info.wezterm_config_dir is not None:
        wezterm_path = platform_info.wezterm_config_dir / "wezterm.lua"
        _report_status(
            runner,
            "windows:wezterm.lua",
            wezterm_path.exists(),
            str(wezterm_path),
        )


def _print_wsl_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
) -> None:
    """Report tools and configs inside the WSL distro."""
    for command in [
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
        "node",
    ]:
        ok, detail = _wsl_command_present(runner, platform_info, command)
        _report_status(runner, f"wsl:{command}", ok, detail)
    if include_starship:
        ok, detail = _wsl_command_present(runner, platform_info, "starship")
        _report_status(runner, "wsl:starship", ok, detail)
    for path in [
        "~/.local/bin/fd",
        "~/.local/bin/bat",
        "~/.tmux.conf",
        "~/.zshrc",
        "~/.config/starship.toml",
        "~/.config/micro/settings.json",
    ]:
        ok, detail = _wsl_file_exists(runner, platform_info, path)
        _report_status(runner, f"wsl:{path}", ok, detail)


def _print_host_report(
    runner: Runner,
    *,
    include_starship: bool,
) -> None:
    """Report tools installed directly on a Linux/macOS host."""
    for command in [
        "wezterm",
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
        "node",
    ]:
        path = runner.which(command)
        _report_status(runner, f"host:{command}", path is not None, path or "")
    if include_starship:
        path = runner.which("starship")
        _report_status(runner, "host:starship", path is not None, path or "")


def print_setup_report(
    runner: Runner,
    platform_info: platform.PlatformInfo,
    *,
    include_starship: bool,
    include_vscode: bool,
) -> None:
    """Print a concise post-setup report of tools and deployed configs."""
    runner.reporter.info("[REPORT] Setup verification summary")

    in_wsl = is_running_in_wsl()
    if platform_info.os == platform.OperatingSystem.WINDOWS:
        _print_windows_report(runner, platform_info, include_starship=include_starship)

    if in_wsl or platform_info.os == platform.OperatingSystem.WINDOWS:
        _print_wsl_report(runner, platform_info, include_starship=include_starship)
    else:
        _print_host_report(runner, include_starship=include_starship)

    if include_vscode and platform_info.os == platform.OperatingSystem.WINDOWS:
        vscode_path = platform_info.vscode_settings_path
        if vscode_path is not None:
            _report_status(
                runner,
                "vscode:settings.json",
                vscode_path.exists(),
                str(vscode_path),
            )


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


def run_setup(  # noqa: PLR0913
    platform_info: platform.PlatformInfo,
    runner: Runner,
    *,
    skip_vscode: bool,
    skip_starship: bool,
    user_install: bool,
    no_sudo: bool,
    uninstall_system_versions: bool,
    keep_system_versions: bool,
    report: bool,
    windows_terminal_cwd: str | None,
    wsl_terminal_cwd: str | None,
) -> int:
    """Run the full setup workflow."""
    runner.reporter.info(f"Detected platform: {platform_info.os.name}")
    runner.reporter.info(f"Package manager: {platform_info.package_manager.name.lower()}")
    if user_install:
        runner.reporter.info("User-install mode: tools will be installed without admin rights")

    in_wsl = is_running_in_wsl()
    if platform_info.os == platform.OperatingSystem.WINDOWS:
        if not platform_info.is_wsl_available:
            runner.reporter.warn("WSL is not available; attempting to install Ubuntu.")
            prerequisites.install_wsl_ubuntu(runner)
        elif not platform_info.is_wsl_default_ubuntu:
            runner.reporter.warn("WSL default is not Ubuntu; attempting to install Ubuntu.")
            prerequisites.install_wsl_ubuntu(runner)

    if in_wsl or platform_info.os == platform.OperatingSystem.WINDOWS:
        if in_wsl:
            runner.reporter.info("Running inside WSL; installing tools into the current distro.")
        prerequisites.ensure_wsl_tools(
            runner,
            platform_info,
            no_sudo=no_sudo or user_install,
            uninstall_system_versions=uninstall_system_versions,
            keep_system_versions=keep_system_versions,
        )
        prerequisites.ensure_wsl_cli_extras(runner, platform_info)
    else:
        prerequisites.ensure_shell_tools(runner, platform_info)
        prerequisites.ensure_host_cli_extras(runner, platform_info)

    prerequisites.ensure_wezterm(
        runner,
        platform_info,
        user_install=user_install,
        no_sudo=no_sudo or user_install,
    )

    prerequisites.ensure_node(runner, platform_info)

    if not skip_starship:
        prerequisites.ensure_starship(runner, platform_info, user_install=user_install)

    configs.deploy_all(
        runner,
        platform_info,
        include_starship=not skip_starship,
        no_sudo=no_sudo,
        wsl_start_dir=wsl_terminal_cwd,
    )

    if not skip_vscode and platform_info.os == platform.OperatingSystem.WINDOWS:
        configs.install_vscode_wsl_extension(runner, platform_info)
        configs.configure_vscode_terminal(
            runner,
            platform_info,
            windows_terminal_cwd=windows_terminal_cwd,
            wsl_terminal_cwd=wsl_terminal_cwd,
        )

    if report:
        print_setup_report(
            runner,
            platform_info,
            include_starship=not skip_starship,
            include_vscode=not skip_vscode,
        )

    runner.reporter.info("Setup complete.")
    if user_install and platform_info.os == platform.OperatingSystem.WINDOWS:
        runner.reporter.info("Restart your terminal for the updated PATH to take effect.")
    if in_wsl:
        runner.reporter.info("Restart your WSL session for the updated PATH to take effect.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    reporter = ConsoleReporter()
    runner = Runner(dry_run=args.dry_run, reporter=reporter)
    platform_info = platform.detect_platform(user_install=args.user_install, no_sudo=args.no_sudo)

    if args.uninstall_system_versions and args.keep_system_versions:
        runner.reporter.error(
            "--uninstall-system-versions and --keep-system-versions are mutually exclusive."
        )
        return 2

    if args.check:
        return run_check(platform_info, runner)

    if args.report_only:
        status = run_check(platform_info, runner)
        print_setup_report(
            runner,
            platform_info,
            include_starship=not args.skip_starship,
            include_vscode=not args.skip_vscode,
        )
        return status

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
        no_sudo=args.no_sudo,
        uninstall_system_versions=args.uninstall_system_versions,
        keep_system_versions=args.keep_system_versions,
        report=args.report,
        windows_terminal_cwd=args.windows_terminal_cwd,
        wsl_terminal_cwd=args.wsl_terminal_cwd,
    )


if __name__ == "__main__":
    sys.exit(main())
