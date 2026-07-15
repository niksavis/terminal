"""Configuration file deployment for WezTerm, tmux, zsh, starship, and micro."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from .platform import OperatingSystem, PlatformInfo, is_running_in_wsl, wsl_exec_command
from .runner import Runner

_REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _REPO_ROOT / "terminal_setup" / "templates"
CHEAT_SHEET_PATH = _REPO_ROOT / "terminal-cheat-sheet.html"
_WSL_START_DIR_PLACEHOLDER = "__WSL_START_DIR__"


def template_path(name: str) -> Path:
    """Return the path to a named template file."""
    return TEMPLATE_DIR / name


def _escape_for_lua_string(value: str) -> str:
    """Escape characters that are special in Lua double-quoted strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _resolve_wsl_start_dir(wsl_start_dir: str | None) -> str:
    """Return the WSL start directory placeholder value for WezTerm template rendering."""
    if wsl_start_dir is None:
        return "$HOME"
    normalized = wsl_start_dir.strip()
    return normalized or "$HOME"


def _is_stale_windows_terminal_cwd(value: str) -> bool:
    """Return True when the value matches an older hardcoded workspace root."""
    normalized = value.strip().replace("/", "\\").rstrip("\\").lower()
    return normalized == "d:\\development"


def deploy_wezterm_config(
    runner: Runner,
    platform: PlatformInfo,
    *,
    wsl_start_dir: str | None = None,
) -> None:
    """Deploy the WezTerm configuration file."""
    if platform.wezterm_config_dir is None:
        return
    runner.ensure_dir(platform.wezterm_config_dir)
    source = template_path("wezterm.lua")
    destination = platform.wezterm_config_dir / "wezterm.lua"
    rendered = source.read_text(encoding="utf-8").replace(
        _WSL_START_DIR_PLACEHOLDER,
        _escape_for_lua_string(_resolve_wsl_start_dir(wsl_start_dir)),
    )
    runner.write_text(destination, rendered)


def deploy_tmux_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the tmux configuration file."""
    destination = platform.home / ".tmux.conf"
    runner.copy(template_path("tmux.conf"), destination)


def deploy_zsh_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the zsh configuration file."""
    destination = platform.home / ".zshrc"
    runner.copy(template_path("zshrc"), destination)


def deploy_starship_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the starship configuration file."""
    config_dir = platform.home / ".config"
    runner.ensure_dir(config_dir)
    destination = config_dir / "starship.toml"
    runner.copy(template_path("starship.toml"), destination)


def deploy_micro_config(runner: Runner, platform: PlatformInfo) -> None:
    """Deploy the micro editor settings file."""
    config_dir = platform.home / ".config" / "micro"
    runner.ensure_dir(config_dir)
    destination = config_dir / "settings.json"
    runner.copy(template_path("micro-settings.json"), destination)


# Marker comment that guards the blocks appended to shell rc files so repeated
# runs stay idempotent and hand-edited rc files are never clobbered.
_STARSHIP_BLOCK_MARKER = "# terminal-setup: starship"
_BASHRC_SOURCE_MARKER = "# terminal-setup: source .bashrc"


def _append_guarded_block(runner: Runner, path: Path, marker: str, block: str) -> bool:
    """Append a marker-guarded block to a file unless the marker already exists.

    Preserves any existing content and returns True only when the block is
    written, so repeated runs are idempotent.
    """
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in existing:
        return False
    prefix = existing
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if prefix:
        prefix += "\n"
    runner.write_text(path, prefix + block)
    return True


def _find_git_bash(platform: PlatformInfo) -> Path | None:
    r"""Return the path to Git for Windows' bash.exe, or None when absent.

    Probes the standard system and per-user install locations. Ignores
    ``C:\Windows\System32\bash.exe``, which is the WSL launcher, not Git Bash.
    """
    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files (x86)/Git/bin/bash.exe"),
        platform.user_programs_dir / "Git" / "bin" / "bash.exe",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _configure_pwsh_starship(runner: Runner, platform: PlatformInfo) -> None:
    """Wire starship into the PowerShell 7 profile (idempotent)."""
    del platform
    if runner.which("pwsh") is None:
        runner.reporter.info("PowerShell 7 (pwsh) not found; skipping its starship prompt setup.")
        return
    # Add-Content with a single-quoted array writes one line per element and
    # avoids PowerShell here-string column rules; none of the lines contain a
    # single quote, so the quoting is safe.
    lines = [
        _STARSHIP_BLOCK_MARKER,
        "if (Get-Command starship -ErrorAction SilentlyContinue) {",
        "    Invoke-Expression (&starship init powershell)",
        "}",
    ]
    ps_array = ",".join(f"'{line}'" for line in lines)
    # Resolve $PROFILE with pwsh itself so the PowerShell-7 path and any
    # OneDrive-redirected Documents folder are honored, then append only once.
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$p = $PROFILE.CurrentUserAllHosts; "
        "$d = Split-Path -Parent $p; "
        "if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }; "
        f"$m = '{_STARSHIP_BLOCK_MARKER}'; "
        "if ((-not (Test-Path $p)) -or (-not (Select-String -Path $p -SimpleMatch $m -Quiet))) "
        f"{{ Add-Content -Path $p -Value {ps_array} }}"
    )
    result = runner.run(["pwsh", "-NoProfile", "-Command", script], check=False)
    if result.returncode != 0:
        runner.reporter.warn(
            "Could not update the PowerShell 7 profile; add "
            "'Invoke-Expression (&starship init powershell)' to $PROFILE manually."
        )


def _configure_git_bash_starship(runner: Runner, platform: PlatformInfo) -> None:
    """Wire starship into Git Bash rc files when Git Bash is installed."""
    if _find_git_bash(platform) is None:
        runner.reporter.info("Git Bash not found; skipping its starship prompt setup.")
        return
    bashrc_block = (
        f"{_STARSHIP_BLOCK_MARKER}\n"
        "if command -v starship >/dev/null 2>&1; then\n"
        '  eval "$(starship init bash)"\n'
        "fi\n"
    )
    _append_guarded_block(runner, platform.home / ".bashrc", _STARSHIP_BLOCK_MARKER, bashrc_block)
    # Login shells read .bash_profile, not .bashrc, so make sure it sources it.
    profile_block = f"{_BASHRC_SOURCE_MARKER}\nif [ -f ~/.bashrc ]; then . ~/.bashrc; fi\n"
    _append_guarded_block(
        runner, platform.home / ".bash_profile", _BASHRC_SOURCE_MARKER, profile_block
    )


def deploy_windows_shell_prompts(runner: Runner, platform: PlatformInfo) -> None:
    """Give the Windows-native shells (PowerShell 7, Git Bash) the starship prompt.

    Deploys the shared starship config to the Windows home and wires starship
    into the pwsh 7 profile and Git Bash rc files. WSL keeps its own setup; cmd
    is left plain because it has no starship prompt hook.
    """
    deploy_starship_config(runner, platform)
    _configure_pwsh_starship(runner, platform)
    _configure_git_bash_starship(runner, platform)


def _wsl_distro(platform: PlatformInfo) -> str:
    """Return the WSL distribution to use, falling back to Ubuntu."""
    return platform.wsl_distribution or "Ubuntu"


def _can_prompt_for_password(runner: Runner) -> bool:
    """Return whether password prompts can reach the user."""
    return runner.dry_run or sys.stdin.isatty()


def set_wsl_default_shell(
    runner: Runner, platform: PlatformInfo, shell: str = "/usr/bin/zsh"
) -> None:
    """Set the default shell inside WSL Ubuntu."""
    distro = _wsl_distro(platform)
    if is_running_in_wsl():
        current_shell = runner.run(
            ["sh", "-c", "getent passwd $(whoami) | cut -d: -f7"],
            check=False,
            dry_run_safe=True,
        ).stdout.strip()
        if current_shell == shell:
            return
        runner.run(["chsh", "-s", shell], interactive=True)
        return
    current_shell = runner.run(
        wsl_exec_command(distro, ["sh", "-c", "getent passwd $(whoami) | cut -d: -f7"]),
        check=False,
        dry_run_safe=True,
    ).stdout.strip()
    if current_shell == shell:
        return
    if not _can_prompt_for_password(runner):
        runner.reporter.warn(
            f"Skipping default shell change to {shell}: chsh needs a password "
            "prompt but stdin is not an interactive terminal."
        )
        return
    # chsh may prompt for the user's password.
    runner.run(wsl_exec_command(distro, ["chsh", "-s", shell]), interactive=True)


def set_host_default_shell(runner: Runner, platform: PlatformInfo, shell: str = "zsh") -> None:
    """Set the default login shell on the host."""
    if platform.os == OperatingSystem.WINDOWS:
        return
    shell_path = runner.which(shell)
    if shell_path is None:
        return
    current_shell = runner.run(
        ["sh", "-c", "getent passwd $(whoami) | cut -d: -f7"], check=False
    ).stdout.strip()
    if current_shell == shell_path:
        return
    if not _can_prompt_for_password(runner):
        runner.reporter.warn(
            f"Skipping default shell change to {shell_path}: chsh needs a password "
            "prompt but stdin is not an interactive terminal."
        )
        return
    # chsh may prompt for the user's password.
    runner.run(["chsh", "-s", shell_path], interactive=True)


def _is_wsl_target(platform: PlatformInfo) -> bool:
    """Return True when configs should be deployed into a WSL distro."""
    return is_running_in_wsl() or platform.os == OperatingSystem.WINDOWS


def deploy_all(  # noqa: PLR0913
    runner: Runner,
    platform: PlatformInfo,
    *,
    include_starship: bool = True,
    include_claude: bool = True,
    claude_nerdfont: bool = True,
    no_sudo: bool = False,
    wsl_start_dir: str | None = None,
) -> None:
    """Deploy all configuration files and set the default shell."""
    deploy_wezterm_config(runner, platform, wsl_start_dir=wsl_start_dir)
    if _is_wsl_target(platform):
        deploy_wsl_configs(runner, platform, include_starship=include_starship)
        if include_starship and platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl():
            deploy_windows_shell_prompts(runner, platform)
        if not no_sudo:
            set_wsl_default_shell(runner, platform)
        else:
            runner.reporter.info("Skipping default shell change because --no-sudo was requested.")
    else:
        deploy_tmux_config(runner, platform)
        deploy_zsh_config(runner, platform)
        deploy_micro_config(runner, platform)
        if include_starship:
            deploy_starship_config(runner, platform)
        if not no_sudo:
            set_host_default_shell(runner, platform)
        else:
            runner.reporter.info("Skipping default shell change because --no-sudo was requested.")
    if include_claude:
        deploy_claude_statusline(runner, platform, nerdfont=claude_nerdfont)


def _to_wsl_path(runner: Runner, distro: str, windows_path: Path) -> str:
    """Convert a Windows path to a WSL path using wslpath."""
    if runner.dry_run:
        drive = windows_path.drive.lower().rstrip(":")
        rest = str(windows_path)[len(windows_path.drive) :].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    result = runner.run(
        wsl_exec_command(distro, ["wslpath", "-u", str(windows_path).replace("\\", "/")]),
        check=True,
    )
    return result.stdout.strip()


def deploy_wsl_configs(
    runner: Runner, platform: PlatformInfo, *, include_starship: bool = True
) -> None:
    """Copy host config templates into the WSL Ubuntu home directory.

    The guest home is resolved as ``$HOME`` inside the distro; it must not be
    derived from the Windows profile name, which routinely differs from the
    Linux username.
    """
    distro = _wsl_distro(platform)
    templates = [
        ("tmux.conf", ".tmux.conf"),
        ("zshrc", ".zshrc"),
        ("micro-settings.json", ".config/micro/settings.json"),
    ]
    if include_starship:
        templates.append(("starship.toml", ".config/starship.toml"))
    for template, target_name in templates:
        source = template_path(template)
        if is_running_in_wsl():
            destination = platform.home / target_name
            runner.ensure_dir(destination.parent)
            runner.copy(source, destination)
        else:
            wsl_source = _to_wsl_path(runner, distro, source)
            parent = target_name.rsplit("/", 1)[0] if "/" in target_name else ""
            mkdir = f'mkdir -p "$HOME/{parent}" && ' if parent else ""
            script = f'{mkdir}cp {shlex.quote(wsl_source)} "$HOME/{target_name}"'
            runner.run(wsl_exec_command(distro, ["sh", "-c", script]))


def _claude_statusline_command(*, nerdfont: bool) -> str:
    """Return the settings.json command that launches the status line script."""
    prefix = "" if nerdfont else "STATUSLINE_NERDFONT=0 "
    return f"{prefix}bash ~/.claude/statusline.sh"


def _claude_wsl_install_script(source: str, *, nerdfont: bool) -> str:
    """Return a POSIX-sh script that installs the status line into a WSL/Linux home.

    Runs inside the target distro; a no-op when Claude Code (``~/.claude``) is absent.
    Merges settings.json with jq so existing keys are preserved.
    """
    command = _claude_statusline_command(nerdfont=nerdfont)
    return (
        'claude="$HOME/.claude"; '
        '[ -d "$claude" ] || { echo "Claude Code not detected ($claude missing); '
        'skipping status line."; exit 0; }; '
        '[ -f "$claude/statusline.sh" ] && echo "Replacing existing $claude/statusline.sh"; '
        f'cp -f {shlex.quote(source)} "$claude/statusline.sh"; '
        's="$claude/settings.json"; [ -f "$s" ] || printf "%s" "{}" > "$s"; '
        'command -v jq >/dev/null 2>&1 || { echo "WARN: jq not found; add the statusLine '
        'block to $s manually"; exit 0; }; '
        'tmp="$(mktemp)"; '
        f"if jq --arg c {shlex.quote(command)} "
        "'.statusLine = {type: \"command\", command: $c, padding: 0}' "
        '"$s" > "$tmp" 2>/dev/null; then mv "$tmp" "$s"; '
        'else rm -f "$tmp"; '
        'echo "WARN: $s is not valid JSON; add the statusLine block manually"; fi'
    )


def deploy_claude_statusline(
    runner: Runner, platform: PlatformInfo, *, nerdfont: bool = True
) -> None:
    """Install the Claude Code status line when Claude Code is present (``~/.claude``).

    Copies the status line script into ``~/.claude`` and registers it in
    ``settings.json``, preserving any existing settings. A no-op (with an info
    message) when Claude Code is not installed. Pass ``nerdfont=False`` for the
    universal build that renders without a Nerd Font.
    """
    source = template_path("statusline.sh")
    if platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl():
        # Claude Code opened inside WSL (WezTerm's default Ubuntu shell).
        distro = _wsl_distro(platform)
        wsl_source = _to_wsl_path(runner, distro, source)
        script = _claude_wsl_install_script(wsl_source, nerdfont=nerdfont)
        runner.run(wsl_exec_command(distro, ["sh", "-c", script]))
        # Claude Code opened natively on Windows (from pwsh 7 or Git Bash) reads
        # %USERPROFILE%\.claude and runs the status line through Git Bash, so the
        # same bash script serves it — but only when Git Bash is installed.
        if _find_git_bash(platform) is None:
            runner.reporter.info(
                "Git Bash not found; skipping the Windows-native Claude status line "
                "(Claude runs the bash script through Git Bash)."
            )
            return
        _deploy_claude_statusline_host(runner, platform, source, nerdfont=nerdfont)
        return
    _deploy_claude_statusline_host(runner, platform, source, nerdfont=nerdfont)


def _deploy_claude_statusline_host(
    runner: Runner, platform: PlatformInfo, source: Path, *, nerdfont: bool
) -> None:
    """Install the status line into the host ``~/.claude`` (no-op when absent)."""
    claude_dir = platform.home / ".claude"
    if not claude_dir.is_dir():
        runner.reporter.info("Claude Code not detected (~/.claude missing); skipping status line.")
        return
    destination = claude_dir / "statusline.sh"
    if destination.exists():
        runner.reporter.info(f"Replacing existing {destination}")
    runner.copy(source, destination)
    settings_path = claude_dir / "settings.json"
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runner.reporter.warn(
                "~/.claude/settings.json is not valid JSON; leaving it unchanged. "
                "Add the statusLine block manually."
            )
            return
    settings["statusLine"] = {
        "type": "command",
        "command": _claude_statusline_command(nerdfont=nerdfont),
        "padding": 0,
    }
    runner.write_text(settings_path, json.dumps(settings, indent=2) + "\n")


def _configure_vscode_terminal_windows(
    settings: dict[str, object],
    platform: PlatformInfo,
    windows_terminal_cwd: str | None,
    wsl_terminal_cwd: str | None,
) -> None:
    """Configure Windows terminal settings for the detected WSL distro."""
    distro = _wsl_distro(platform)
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    if not isinstance(profiles, dict):
        profiles = {}

    if windows_terminal_cwd is not None:
        normalized_windows_cwd = windows_terminal_cwd.strip()
        if normalized_windows_cwd:
            settings["terminal.integrated.cwd"] = normalized_windows_cwd
        else:
            settings.pop("terminal.integrated.cwd", None)
    else:
        existing_cwd = settings.get("terminal.integrated.cwd")
        if isinstance(existing_cwd, str) and _is_stale_windows_terminal_cwd(existing_cwd):
            settings.pop("terminal.integrated.cwd", None)

    # Remove synthetic profile from older setup versions.
    profiles.pop("WSL (Default)", None)

    # Remove stale Ubuntu profile when the active distro is a different Ubuntu variant.
    if distro.lower() != "ubuntu":
        profiles.pop("Ubuntu (WSL)", None)

    profile_name = f"{distro} (WSL)"
    profile_args = ["-d", distro]
    if wsl_terminal_cwd is not None:
        normalized_wsl_cwd = wsl_terminal_cwd.strip()
        if normalized_wsl_cwd:
            profile_args.extend(["--cd", normalized_wsl_cwd])

    profiles[profile_name] = {
        "path": "C:\\Windows\\System32\\wsl.exe",
        "args": profile_args,
        "icon": "terminal-ubuntu",
    }

    settings["terminal.integrated.defaultProfile.windows"] = profile_name
    settings["terminal.integrated.profiles.windows"] = profiles


def configure_vscode_terminal(
    runner: Runner,
    platform: PlatformInfo,
    *,
    windows_terminal_cwd: str | None = None,
    wsl_terminal_cwd: str | None = None,
) -> None:
    """Update VS Code settings to use the configured terminal.

    Pass optional cwd values via CLI flags when user-specific defaults are desired.
    """
    if platform.vscode_settings_path is None:
        return
    settings_path = platform.vscode_settings_path
    settings: dict[str, object] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            runner.reporter.warn(
                "VS Code settings.json is not strict JSON; skipping terminal profile update "
                "to avoid overwriting existing settings."
            )
            return

    if platform.os == OperatingSystem.WINDOWS:
        _configure_vscode_terminal_windows(
            settings,
            platform,
            windows_terminal_cwd,
            wsl_terminal_cwd,
        )
    elif platform.os == OperatingSystem.LINUX:
        settings["terminal.integrated.defaultProfile.linux"] = "zsh"
    elif platform.os == OperatingSystem.MACOS:
        settings["terminal.integrated.defaultProfile.osx"] = "zsh"

    runner.ensure_dir(settings_path.parent)
    runner.write_text(settings_path, json.dumps(settings, indent=2) + "\n")


def ensure_vscode_extension(runner: Runner, extension_id: str) -> None:
    """Install a VS Code extension if code is available.

    Extension installs are a convenience; a failing VS Code CLI must not
    abort the rest of the setup.
    """
    code_path = runner.which("code")
    if code_path is None:
        return
    if code_path.lower().endswith((".cmd", ".bat")):
        command = ["cmd", "/c", code_path, "--install-extension", extension_id]
    else:
        command = [code_path, "--install-extension", extension_id]
    result = runner.run(command, check=False)
    if result.returncode != 0:
        runner.reporter.warn(
            f"VS Code extension install failed for {extension_id} "
            f"(exit {result.returncode}); install it manually from VS Code."
        )


def install_vscode_wsl_extension(runner: Runner, platform: PlatformInfo) -> None:
    """Install the VS Code Remote - WSL extension on Windows."""
    if platform.os != OperatingSystem.WINDOWS:
        return
    ensure_vscode_extension(runner, "ms-vscode-remote.remote-wsl")
