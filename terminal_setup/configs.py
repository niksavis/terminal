from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
from pathlib import Path, PureWindowsPath

from .platform import OperatingSystem, PlatformInfo, is_running_in_wsl, wsl_exec_command
from .prerequisites import _add_to_user_path, attempt
from .runner import Runner

_REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _REPO_ROOT / "terminal_setup" / "templates"
CHEAT_SHEET_PATH = _REPO_ROOT / "terminal-cheat-sheet.html"
IMG_ZOOM_SOURCE = _REPO_ROOT / "terminal_setup" / "img_zoom_tool"
_WSL_START_DIR_PLACEHOLDER = "__WSL_START_DIR__"


def template_path(name: str) -> Path:
    return TEMPLATE_DIR / name


def _escape_for_lua_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_WSL_START_DIR_FORBIDDEN = ('"', "`", "$(", "\\", "\n")


def _resolve_wsl_start_dir(wsl_start_dir: str | None) -> str:

    if wsl_start_dir is None:
        return "$HOME"
    normalized = wsl_start_dir.strip()
    if not normalized:
        return "$HOME"
    for token in _WSL_START_DIR_FORBIDDEN:
        if token in normalized:
            message = (
                f"--wsl-terminal-cwd must not contain {token!r}; the value is embedded "
                "in the WezTerm startup shell command"
            )
            raise ValueError(message)
    return normalized


def _is_stale_windows_terminal_cwd(value: str) -> bool:
    normalized = value.strip().replace("/", "\\").rstrip("\\").lower()
    return normalized == "d:\\development"


def deploy_wezterm_config(
    runner: Runner,
    platform: PlatformInfo,
    *,
    wsl_start_dir: str | None = None,
) -> None:
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
    destination = platform.home / ".tmux.conf"
    runner.copy(template_path("tmux.conf"), destination)


def deploy_zsh_config(runner: Runner, platform: PlatformInfo) -> None:
    destination = platform.home / ".zshrc"
    runner.copy(template_path("zshrc"), destination)


def deploy_starship_config(runner: Runner, platform: PlatformInfo) -> None:
    config_dir = platform.home / ".config"
    runner.ensure_dir(config_dir)
    destination = config_dir / "starship.toml"
    runner.copy(template_path("starship.toml"), destination)


def deploy_micro_config(runner: Runner, platform: PlatformInfo) -> None:
    config_dir = platform.home / ".config" / "micro"
    runner.ensure_dir(config_dir)
    destination = config_dir / "settings.json"
    runner.copy(template_path("micro-settings.json"), destination)


_STARSHIP_BLOCK_MARKER = "# terminal-setup: starship"
_BASHRC_SOURCE_MARKER = "# terminal-setup: source .bashrc"


def _append_guarded_block(runner: Runner, path: Path, marker: str, block: str) -> bool:

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

    candidates = [
        Path("C:/Program Files/Git/bin/bash.exe"),
        Path("C:/Program Files (x86)/Git/bin/bash.exe"),
        platform.user_programs_dir / "Git" / "bin" / "bash.exe",
    ]
    return next((candidate for candidate in candidates if candidate.exists()), None)


def _configure_pwsh_starship(runner: Runner, platform: PlatformInfo) -> None:
    del platform
    if runner.which("pwsh") is None:
        runner.reporter.info("PowerShell 7 (pwsh) not found; skipping its starship prompt setup.")
        return
    lines = [
        _STARSHIP_BLOCK_MARKER,
        "if (Get-Command starship -ErrorAction SilentlyContinue) {",
        "    Invoke-Expression (&starship init powershell)",
        "}",
    ]
    ps_array = ",".join(f"'{line}'" for line in lines)
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "$p = $PROFILE.CurrentUserAllHosts; "
        "$d = Split-Path -Parent $p; "
        "if (-not (Test-Path $d)) { New-Item -ItemType Directory -Path $d -Force | Out-Null }; "
        f"$m = '{_STARSHIP_BLOCK_MARKER}'; "
        "if ((-not (Test-Path $p)) -or (-not (Select-String -Path $p -SimpleMatch $m -Quiet))) "
        f"{{ Add-Content -Path $p -Value {ps_array} }}"
    )
    result = runner.run(
        ["pwsh", "-NoProfile", "-Command", script],
        check=False,
        label="add the starship prompt to the PowerShell profile",
    )
    if result.returncode != 0:
        runner.reporter.warn(
            "Could not update the PowerShell 7 profile; add "
            "'Invoke-Expression (&starship init powershell)' to $PROFILE manually."
        )


def _configure_git_bash_starship(runner: Runner, platform: PlatformInfo) -> None:
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
    profile_block = f"{_BASHRC_SOURCE_MARKER}\nif [ -f ~/.bashrc ]; then . ~/.bashrc; fi\n"
    _append_guarded_block(
        runner, platform.home / ".bash_profile", _BASHRC_SOURCE_MARKER, profile_block
    )


def deploy_windows_shell_prompts(runner: Runner, platform: PlatformInfo) -> None:

    deploy_starship_config(runner, platform)
    _configure_pwsh_starship(runner, platform)
    _configure_git_bash_starship(runner, platform)


def _wsl_distro(platform: PlatformInfo) -> str:
    return platform.wsl_distribution or "Ubuntu"


def _can_prompt_for_password(runner: Runner) -> bool:
    return runner.dry_run or sys.stdin.isatty()


def set_wsl_default_shell(
    runner: Runner, platform: PlatformInfo, shell: str = "/usr/bin/zsh"
) -> None:
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
    runner.run(wsl_exec_command(distro, ["chsh", "-s", shell]), interactive=True)


def set_host_default_shell(runner: Runner, platform: PlatformInfo, shell: str = "zsh") -> None:
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
    runner.run(["chsh", "-s", shell_path], interactive=True)


def _is_wsl_target(platform: PlatformInfo) -> bool:
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
        deploy_claude_img_zoom_skill(runner, platform)
        attempt(
            runner,
            "install the basicly cli-tools skills",
            lambda: deploy_claude_cli_tools_skills(runner, platform),
        )


def _to_wsl_path(runner: Runner, distro: str, windows_path: Path) -> str:
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
            runner.run(
                wsl_exec_command(distro, ["sh", "-c", script]), label=f"write ~/{target_name}"
            )


def _claude_statusline_command(*, nerdfont: bool) -> str:
    prefix = "" if nerdfont else "STATUSLINE_NERDFONT=0 "
    return f"{prefix}bash ~/.claude/statusline.sh"


def _claude_wsl_install_script(source: str, *, nerdfont: bool) -> str:

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

    source = template_path("statusline.sh")
    if platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl():
        distro = _wsl_distro(platform)
        wsl_source = _to_wsl_path(runner, distro, source)
        script = _claude_wsl_install_script(wsl_source, nerdfont=nerdfont)
        runner.run(
            wsl_exec_command(distro, ["sh", "-c", script]),
            label="install the Claude Code status line",
        )
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


_UV_MISSING = "uv not found in PATH or ~/.local/bin; install uv, then re-run terminal-setup"
_IMG_ZOOM_SKILL = "img-zoom"
_IMG_ZOOM_STAGE_POSIX = "$HOME/.local/share/terminal-setup/img_zoom_tool"


def _is_windows_host(platform: PlatformInfo) -> bool:
    return platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()


_UV_RESOLVE_POSIX = (
    'uv="${UV:-}"; [ -x "$uv" ] || uv="$(command -v uv)" || uv="$HOME/.local/bin/uv"; '
    f'[ -x "$uv" ] || {{ echo "{_UV_MISSING}" >&2; exit 1; }}; '
)


def _img_zoom_install_script(source: str, *, update: bool) -> str:
    upgrade = " --upgrade" if update else ""
    return (
        _UV_RESOLVE_POSIX + f'dest="{_IMG_ZOOM_STAGE_POSIX}"; '
        'rm -rf "$dest" && mkdir -p "$dest" && '
        f'cp -R {shlex.quote(source)}/. "$dest"/ && '
        'find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} + || exit 1; '
        f'"$uv" tool install{upgrade} "$dest"'
    )


def _windows_img_zoom_stage(platform: PlatformInfo) -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else platform.home / "AppData" / "Local"
    return base / "terminal-setup" / "img_zoom_tool"


def _stage_img_zoom_source(runner: Runner, destination: Path) -> None:
    runner.reporter.info(f"stage img-zoom source in {destination}")
    if runner.dry_run:
        return
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        IMG_ZOOM_SOURCE,
        destination,
        ignore=shutil.ignore_patterns("__pycache__"),
        copy_function=shutil.copyfile,
    )


def install_img_zoom_wsl(runner: Runner, platform: PlatformInfo, *, update: bool = False) -> None:
    distro = _wsl_distro(platform)
    source = _to_wsl_path(runner, distro, IMG_ZOOM_SOURCE)
    script = _img_zoom_install_script(source, update=update)
    runner.run(wsl_exec_command(distro, ["sh", "-c", script]), label="install img-zoom")


def _windows_uv(runner: Runner, platform: PlatformInfo) -> str:
    for candidate in (os.environ.get("UV"), runner.which("uv")):
        if candidate:
            return candidate
    fallback = platform.home / ".local" / "bin" / "uv.exe"
    if fallback.exists():
        return str(fallback)
    raise RuntimeError(_UV_MISSING)


def install_img_zoom_native(
    runner: Runner, platform: PlatformInfo, *, update: bool = False
) -> None:
    if not _is_windows_host(platform):
        script = _img_zoom_install_script(IMG_ZOOM_SOURCE.as_posix(), update=update)
        runner.run(["sh", "-c", script], label="install img-zoom")
        return
    uv = _windows_uv(runner, platform)
    stage = _windows_img_zoom_stage(platform)
    _stage_img_zoom_source(runner, stage)
    upgrade = ["--upgrade"] if update else []
    runner.run([uv, "tool", "install", *upgrade, str(stage)])
    bin_dir = runner.run([uv, "tool", "dir", "--bin"], dry_run_safe=True).stdout.strip()
    if bin_dir:
        _add_to_user_path(runner, Path(bin_dir))


def _native_img_zoom_present(runner: Runner, platform: PlatformInfo) -> bool:
    if runner.which("img-zoom"):
        return True
    local_bin = platform.home / ".local" / "bin"
    return (local_bin / "img-zoom").exists() or (local_bin / "img-zoom.exe").exists()


def _claude_skill_wsl_install_script(source: str, name: str) -> str:
    return (
        'claude="$HOME/.claude"; '
        f'[ -d "$claude" ] || {{ echo "Claude Code not detected ($claude missing); '
        f'skipping the {name} skill."; exit 0; }}; '
        f'{{ command -v {name} >/dev/null 2>&1 || [ -x "$HOME/.local/bin/{name}" ]; }} || '
        f'{{ echo "{name} is not installed in WSL; skipping the {name} skill."; exit 0; }}; '
        f'mkdir -p "$claude/skills/{name}"; '
        f'cp -f {shlex.quote(source)} "$claude/skills/{name}/SKILL.md"'
    )


def _deploy_img_zoom_skill_native(runner: Runner, platform: PlatformInfo, source: Path) -> None:
    claude_dir = platform.home / ".claude"
    if not claude_dir.is_dir():
        runner.reporter.info(
            "Claude Code not detected (~/.claude missing); skipping the img-zoom skill."
        )
        return
    if not _native_img_zoom_present(runner, platform):
        runner.reporter.info("img-zoom is not installed here; skipping the img-zoom skill.")
        return
    runner.copy(source, claude_dir / "skills" / _IMG_ZOOM_SKILL / "SKILL.md")


def deploy_claude_img_zoom_skill(runner: Runner, platform: PlatformInfo) -> None:
    source = template_path("img-zoom-skill.md")
    if _is_windows_host(platform):
        distro = _wsl_distro(platform)
        wsl_source = _to_wsl_path(runner, distro, source)
        script = _claude_skill_wsl_install_script(wsl_source, _IMG_ZOOM_SKILL)
        runner.run(
            wsl_exec_command(distro, ["sh", "-c", script]), label="install the img-zoom skill"
        )
    _deploy_img_zoom_skill_native(runner, platform, source)


BASICLY_REF = "v0.18.9"
BASICLY_SPEC = f"git+https://github.com/niksavis/basicly@{BASICLY_REF}"
CLI_TOOLS_SKILL = "cli-tools"
TOOL_SKILL_COMMANDS: dict[str, tuple[str, ...]] = {
    "tool-ast-grep": ("ast-grep",),
    "tool-bat": ("bat", "batcat"),
    "tool-curl": ("curl",),
    "tool-direnv": ("direnv",),
    "tool-fd": ("fd", "fdfind"),
    "tool-fzf": ("fzf",),
    "tool-git": ("git",),
    "tool-git-delta": ("delta",),
    "tool-git-lfs": ("git-lfs",),
    "tool-jq": ("jq",),
    "tool-just": ("just",),
    "tool-lazygit": ("lazygit",),
    "tool-ripgrep": ("rg",),
    "tool-sd": ("sd",),
    "tool-shellcheck": ("shellcheck",),
    "tool-starship": ("starship",),
    "tool-tmux": ("tmux",),
    "tool-tree": ("tree",),
    "tool-typos": ("typos",),
    "tool-uv": ("uv",),
    "tool-wezterm": ("wezterm",),
    "tool-wget": ("wget",),
    "tool-xh": ("xh",),
    "tool-yq": ("yq",),
    "tool-zsh": ("zsh",),
}
_CLI_TOOLS_LABEL = "install the basicly cli-tools skills"
_SKILLS_USER = ["tool", "run", "--from", BASICLY_SPEC, "basicly", "skills-user"]


def _cli_tools_skills_script() -> str:
    checks = "".join(
        "if "
        + " || ".join(
            f'command -v {command} >/dev/null 2>&1 || [ -x "$HOME/.local/bin/{command}" ]'
            for command in commands
        )
        + f'; then set -- "$@" {skill}; fi; '
        for skill, commands in TOOL_SKILL_COMMANDS.items()
    )
    return (
        '[ -d "$HOME/.claude" ] || { echo "Claude Code not detected ($HOME/.claude missing); '
        'skipping the cli-tools skills."; exit 0; }; '
        + _UV_RESOLVE_POSIX
        + f"set -- {CLI_TOOLS_SKILL}; "
        + checks
        + '"$uv" '
        + " ".join(shlex.quote(part) for part in _SKILLS_USER)
        + ' "$@"'
    )


def _is_windows_builtin(path: str) -> bool:
    system_root = PureWindowsPath(os.environ.get("SYSTEMROOT") or "C:\\Windows")
    return PureWindowsPath(path).is_relative_to(system_root)


def _native_tool_present(runner: Runner, platform: PlatformInfo, command: str) -> bool:
    found = runner.which(command)
    if found and not _is_windows_builtin(found):
        return True
    local_bin = platform.home / ".local" / "bin"
    return (local_bin / command).exists() or (local_bin / f"{command}.exe").exists()


def _deploy_cli_tools_skills_windows(runner: Runner, platform: PlatformInfo) -> None:
    if not (platform.home / ".claude").is_dir():
        runner.reporter.info(
            "Claude Code not detected (~/.claude missing); skipping the cli-tools skills."
        )
        return
    skills = [
        skill
        for skill, commands in TOOL_SKILL_COMMANDS.items()
        if any(_native_tool_present(runner, platform, command) for command in commands)
    ]
    uv = _windows_uv(runner, platform)
    runner.run([uv, *_SKILLS_USER, "--home", str(platform.home), CLI_TOOLS_SKILL, *skills])


def deploy_claude_cli_tools_skills(runner: Runner, platform: PlatformInfo) -> None:
    script = _cli_tools_skills_script()
    if not _is_windows_host(platform):
        runner.run(["sh", "-c", script], label=_CLI_TOOLS_LABEL)
        return
    runner.run(
        wsl_exec_command(_wsl_distro(platform), ["sh", "-c", script]), label=_CLI_TOOLS_LABEL
    )
    _deploy_cli_tools_skills_windows(runner, platform)


def _configure_vscode_terminal_windows(
    settings: dict[str, object],
    platform: PlatformInfo,
    windows_terminal_cwd: str | None,
    wsl_terminal_cwd: str | None,
) -> None:
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

    profiles.pop("WSL (Default)", None)

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
    if platform.os != OperatingSystem.WINDOWS:
        return
    ensure_vscode_extension(runner, "ms-vscode-remote.remote-wsl")
