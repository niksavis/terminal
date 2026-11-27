from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from . import harness
from .platform import OperatingSystem, PlatformInfo, is_running_in_wsl, wsl_exec_command
from .prerequisites import (
    SKIPPED_OFFLINE,
    _add_to_user_path,
    attempt,
    github_unreachable,
    root_shell_command,
)
from .prompt_config import configure_zshenv, write_starship_config
from .runner import Runner

_REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _REPO_ROOT / "terminal_setup" / "templates"
CHEAT_SHEET_PATH = _REPO_ROOT / "terminal-cheat-sheet.html"
IMG_ZOOM_SOURCE = _REPO_ROOT / "terminal_setup" / "img_zoom_tool"
_WSL_START_DIR_PLACEHOLDER = "__WSL_START_DIR__"
_HERDR_PLACEHOLDER = "__HERDR_INSTALLED__"
_WSL_DEFAULT_DISTRO_PLACEHOLDER = "__WSL_DEFAULT_DISTRO__"
_WSL_DISTRO_NAME = re.compile(r"[A-Za-z0-9._-]+")


def template_path(name: str) -> Path:
    return TEMPLATE_DIR / name


def _escape_for_lua_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _lua_wsl_distro(name: str | None) -> str:
    if name is None or _WSL_DISTRO_NAME.fullmatch(name) is None:
        return ""
    return name


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
    herdr: bool = False,
) -> None:
    if platform.wezterm_config_dir is None:
        return
    runner.ensure_dir(platform.wezterm_config_dir)
    source = template_path("wezterm.lua")
    destination = platform.wezterm_config_dir / "wezterm.lua"
    rendered = (
        source
        .read_text(encoding="utf-8")
        .replace(
            _WSL_START_DIR_PLACEHOLDER,
            _escape_for_lua_string(_resolve_wsl_start_dir(wsl_start_dir)),
        )
        .replace(_HERDR_PLACEHOLDER, "true" if herdr else "false")
        .replace(_WSL_DEFAULT_DISTRO_PLACEHOLDER, _lua_wsl_distro(platform.wsl_distribution))
    )
    runner.write_text(destination, rendered)


BACKUP_SUFFIX = ".terminal-setup.bak"


def _backup_message(target_name: str) -> str:
    message = f"Kept the old ~/{target_name} as ~/{target_name}{BACKUP_SUFFIX}"
    if target_name == ".zshrc":
        message += "; put your own lines in ~/.zshrc.local, which setup never overwrites"
    return message


def _deploy_template(runner: Runner, source: Path, home: Path, target_name: str) -> None:
    destination = home / target_name
    if destination.is_file() and destination.read_text(encoding="utf-8") != source.read_text(
        encoding="utf-8"
    ):
        runner.copy(destination, destination.with_name(destination.name + BACKUP_SUFFIX))
        if not runner.dry_run:
            runner.reporter.info(_backup_message(target_name))
    runner.copy(source, destination)


def deploy_tmux_config(runner: Runner, platform: PlatformInfo) -> None:
    _deploy_template(runner, template_path("tmux.conf"), platform.home, ".tmux.conf")


def deploy_zsh_config(runner: Runner, platform: PlatformInfo) -> None:
    _deploy_template(runner, template_path("zshrc"), platform.home, ".zshrc")
    if not runner.dry_run:
        configure_zshenv(platform.home)


def deploy_starship_config(runner: Runner, platform: PlatformInfo) -> None:
    config_dir = platform.home / ".config"
    runner.ensure_dir(config_dir)
    if runner.dry_run:
        runner.reporter.info("write ~/.config/starship.toml")
        return
    bridge = runner.which("starship.exe") if is_running_in_wsl() else None
    if write_starship_config(platform.home, template_path("starship.toml"), bridge):
        runner.reporter.info(_backup_message(".config/starship.toml"))


def deploy_micro_config(runner: Runner, platform: PlatformInfo) -> None:
    config_dir = platform.home / ".config" / "micro"
    runner.ensure_dir(config_dir)
    _deploy_template(
        runner, template_path("micro-settings.json"), platform.home, ".config/micro/settings.json"
    )


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
    return not runner.unattended and (runner.dry_run or sys.stdin.isatty())


def _set_shell_unattended(runner: Runner, shell: str, *, wsl_distro: str | None) -> bool:
    if not runner.unattended:
        return False
    whoami = ["id", "-un"]
    if wsl_distro and not is_running_in_wsl():
        whoami = wsl_exec_command(wsl_distro, whoami)
    user = runner.run(whoami, check=False, dry_run_safe=True).stdout.strip()
    if not user:
        return False
    command = root_shell_command(
        runner, f"chsh -s {shlex.quote(shell)} {shlex.quote(user)}", wsl_distro=wsl_distro
    )
    if command is None:
        return False
    runner.run(command, label=f"set the default shell to {shell}")
    return True


def _skip_shell_change(runner: Runner, shell: str, *, wsl_distro: str | None) -> None:
    if _set_shell_unattended(runner, shell, wsl_distro=wsl_distro):
        return
    runner.reporter.warn(
        f"Skipping default shell change to {shell}: chsh needs a password "
        "prompt but stdin is not an interactive terminal."
    )
    where = "in WSL" if wsl_distro or is_running_in_wsl() else "in a terminal"
    runner.reporter.step(f"To change it, run this {where}: chsh -s {shell}")


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
        if not _can_prompt_for_password(runner):
            _skip_shell_change(runner, shell, wsl_distro=None)
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
        _skip_shell_change(runner, shell, wsl_distro=distro)
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
        _skip_shell_change(runner, shell_path, wsl_distro=None)
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
    herdr: bool = False,
) -> None:
    deploy_wezterm_config(runner, platform, wsl_start_dir=wsl_start_dir, herdr=herdr)
    if _is_wsl_target(platform):
        deploy_wsl_configs(runner, platform, include_starship=include_starship)
        if platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl():
            deploy_wsl_wezterm_config(runner, platform)
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


_WSL_DRIVE_ROOTS: dict[tuple[str, str], str] = {}
_DRIVE = re.compile(r"[A-Za-z]:")


def _to_wsl_path(runner: Runner, distro: str, windows_path: Path) -> str:
    drive = windows_path.drive
    rest = str(windows_path)[len(drive) :].replace("\\", "/")
    if runner.dry_run:
        return f"/mnt/{drive.lower().rstrip(':')}{rest}"
    if _DRIVE.fullmatch(drive) is None:
        result = runner.run(
            wsl_exec_command(distro, ["wslpath", "-u", str(windows_path).replace("\\", "/")]),
            check=True,
        )
        return result.stdout.strip()
    key = (distro, drive.upper())
    root = _WSL_DRIVE_ROOTS.get(key)
    if root is None:
        result = runner.run(wsl_exec_command(distro, ["wslpath", "-u", f"{drive}/"]), check=True)
        root = result.stdout.strip().rstrip("/")
        _WSL_DRIVE_ROOTS[key] = root
    return f"{root}{rest}"


def deploy_wsl_configs(
    runner: Runner, platform: PlatformInfo, *, include_starship: bool = True
) -> None:

    distro = _wsl_distro(platform)
    templates = [
        ("tmux.conf", ".tmux.conf"),
        ("zshrc", ".zshrc"),
        ("micro-settings.json", ".config/micro/settings.json"),
    ]
    for template, target_name in templates:
        source = template_path(template)
        if is_running_in_wsl():
            runner.ensure_dir((platform.home / target_name).parent)
            _deploy_template(runner, source, platform.home, target_name)
        else:
            wsl_source = _to_wsl_path(runner, distro, source)
            parent = target_name.rsplit("/", 1)[0] if "/" in target_name else ""
            mkdir = f'mkdir -p "$HOME/{parent}" || exit 1; ' if parent else ""
            quoted = shlex.quote(wsl_source)
            target = f'"$HOME/{target_name}"'
            backup = f'"$HOME/{target_name}{BACKUP_SUFFIX}"'
            script = (
                f"{mkdir}if [ -f {target} ] && ! cmp -s {quoted} {target}; then "
                f"cp -f {target} {backup} || exit 1; "
                f"echo {shlex.quote(_backup_message(target_name))}; fi; "
                f"cp {quoted} {target}"
            )
            result = runner.run(
                wsl_exec_command(distro, ["sh", "-c", script]), label=f"write ~/{target_name}"
            )
            for line in (result.stdout or "").splitlines():
                runner.reporter.info(line)

    if is_running_in_wsl():
        if not runner.dry_run:
            configure_zshenv(platform.home)
        if include_starship:
            deploy_starship_config(runner, platform)
    else:
        helper = _to_wsl_path(runner, distro, Path(__file__).with_name("prompt_config.py"))
        script = (
            'PATH="$HOME/.local/bin:$PATH"; '
            "uv run --no-project --no-python-downloads --python 3.14 python "
            f'{shlex.quote(helper)} --home "$HOME/" --zsh --wsl'
        )
        if include_starship:
            source = _to_wsl_path(runner, distro, template_path("starship.toml"))
            script += f" --starship-template {shlex.quote(source)}"
        result = runner.run(
            wsl_exec_command(distro, ["sh", "-c", script]),
            label="configure WSL prompt performance",
        )
        for line in (result.stdout or "").splitlines():
            runner.reporter.info(line)


_WSL_WEZTERM_TARGET = ".config/wezterm/wezterm.lua"


def wsl_wezterm_config_script(wsl_source: str) -> str:
    target = f'"$HOME/{_WSL_WEZTERM_TARGET}"'
    return (
        'PATH="$HOME/.local/bin:$PATH"; '
        f"if [ -f {target} ] || command -v wezterm >/dev/null 2>&1; then "
        'mkdir -p "$HOME/.config/wezterm" || exit 1; '
        f"cp -f {shlex.quote(wsl_source)} {target} || exit 1; "
        f'echo "Updated ~/{_WSL_WEZTERM_TARGET} for the WezTerm in WSL"; fi'
    )


def deploy_wsl_wezterm_config(runner: Runner, platform: PlatformInfo) -> None:
    if platform.wezterm_config_dir is None:
        return
    distro = _wsl_distro(platform)
    wsl_source = _to_wsl_path(runner, distro, platform.wezterm_config_dir / "wezterm.lua")
    result = runner.run(
        wsl_exec_command(distro, ["sh", "-c", wsl_wezterm_config_script(wsl_source)]),
        label=f"write ~/{_WSL_WEZTERM_TARGET} when WezTerm is in WSL",
    )
    for line in (result.stdout or "").splitlines():
        runner.reporter.info(line)


_STATUSLINE_TAP = "orch-statusline-tap"
_STATUSLINE_RUN = "bash ~/.claude/statusline.sh"
_STATUSLINE_UNIVERSAL = "STATUSLINE_NERDFONT=0 "
_STATUSLINE_PLAIN_FORMS = (_STATUSLINE_RUN, _STATUSLINE_UNIVERSAL + _STATUSLINE_RUN)
_STATUSLINE_KEPT = "Kept the statusLine command that wraps statusline.sh"


def _claude_statusline_command(*, nerdfont: bool, tap: bool = False) -> str:
    prefix = "" if nerdfont else _STATUSLINE_UNIVERSAL
    if not tap:
        return f"{prefix}{_STATUSLINE_RUN}"
    return (
        f"if command -v {_STATUSLINE_TAP} >/dev/null 2>&1; "
        f"then {prefix}exec {_STATUSLINE_TAP} -- {_STATUSLINE_RUN}; "
        f"else {prefix}exec {_STATUSLINE_RUN}; fi"
    )


def _keeps_statusline_command(existing: object) -> bool:
    return (
        isinstance(existing, str)
        and "statusline.sh" in existing
        and existing not in _STATUSLINE_PLAIN_FORMS
    )


def _claude_wsl_install_script(source: str, *, nerdfont: bool) -> str:
    plain = _claude_statusline_command(nerdfont=nerdfont)
    wrapped = _claude_statusline_command(nerdfont=nerdfont, tap=True)
    keep_test = " && ".join(
        f'[ "$cur" != {shlex.quote(form)} ]' for form in _STATUSLINE_PLAIN_FORMS
    )
    return (
        'PATH="$HOME/.local/bin:$PATH"; '
        'claude="$HOME/.claude"; '
        '[ -d "$claude" ] || { echo "Claude Code not detected ($claude missing); '
        'skipping status line."; exit 0; }; '
        '[ -f "$claude/statusline.sh" ] && echo "Replacing existing $claude/statusline.sh"; '
        f'cp -f {shlex.quote(source)} "$claude/statusline.sh"; '
        's="$claude/settings.json"; [ -f "$s" ] || printf "%s" "{}" > "$s"; '
        'command -v jq >/dev/null 2>&1 || { echo "WARN: jq not found; add the statusLine '
        'block to $s manually"; exit 0; }; '
        'cur="$(jq -r \'(.statusLine | objects | .command | strings) // empty\' "$s" '
        '2>/dev/null)"; '
        f'case "$cur" in *statusline.sh*) if {keep_test}; then '
        f"echo {shlex.quote(_STATUSLINE_KEPT)}; exit 0; fi;; esac; "
        f"if command -v {_STATUSLINE_TAP} >/dev/null 2>&1; then c={shlex.quote(wrapped)}; "
        f"else c={shlex.quote(plain)}; fi; "
        'tmp="$(mktemp)"; '
        'if jq --arg c "$c" '
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
    current = settings.get("statusLine")
    if isinstance(current, dict) and _keeps_statusline_command(current.get("command")):
        runner.reporter.info(_STATUSLINE_KEPT)
        return
    tap = runner.which(_STATUSLINE_TAP) is not None
    settings["statusLine"] = {
        "type": "command",
        "command": _claude_statusline_command(nerdfont=nerdfont, tap=tap),
        "padding": 0,
    }
    runner.write_text(settings_path, json.dumps(settings, indent=2) + "\n")


_UV_MISSING = (
    "uv not found in PATH or ~/.local/bin; install it with the install.ps1 or install.sh "
    "bootstrap from the README, which then runs this setup"
)
_IMG_ZOOM_SKILL = "img-zoom"
_IMG_ZOOM_STAGE_POSIX = "$HOME/.local/share/terminal-setup/img_zoom_tool"
_IMG_ZOOM_STAMP = ".terminal-setup-stamp"
_IMG_ZOOM_REFRESH_DAYS = 30


def _is_windows_host(platform: PlatformInfo) -> bool:
    return platform.os == OperatingSystem.WINDOWS and not is_running_in_wsl()


_UV_RESOLVE_POSIX = (
    'uv="${UV:-}"; [ -x "$uv" ] || uv="$(command -v uv)" || uv="$HOME/.local/bin/uv"; '
    f'[ -x "$uv" ] || {{ echo "{_UV_MISSING}" >&2; exit 1; }}; '
)


def img_zoom_digest() -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in IMG_ZOOM_SOURCE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    for path in files:
        digest.update(b"\0" + path.relative_to(IMG_ZOOM_SOURCE).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _img_zoom_install_script(source: str, *, update: bool, digest: str) -> str:
    upgrade = " --upgrade" if update else ""
    return (
        f'dest="{_IMG_ZOOM_STAGE_POSIX}"; stamp="$dest/{_IMG_ZOOM_STAMP}"; '
        f'if [ "$(cat "$stamp" 2>/dev/null)" = "{digest}" ] && '
        f'[ -n "$(find "$stamp" -mtime -{_IMG_ZOOM_REFRESH_DAYS} 2>/dev/null)" ] && '
        '{ [ -x "$HOME/.local/bin/img-zoom" ] || command -v img-zoom >/dev/null 2>&1; }; '
        'then echo "img-zoom is current"; exit 0; fi; '
        + _UV_RESOLVE_POSIX
        + f'src={source}; [ -n "$src" ] || exit 1; '
        'rm -rf "$dest" && mkdir -p "$dest" && '
        'cp -R "$src"/. "$dest"/ && '
        'find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} + || exit 1; '
        f'"$uv" tool install{upgrade} "$dest" && printf "%s\\n" "{digest}" > "$stamp"'
    )


def _windows_img_zoom_stage(platform: PlatformInfo) -> Path:
    return platform.setup_data_dir / "img_zoom_tool"


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
    windows_source = shlex.quote(str(IMG_ZOOM_SOURCE).replace("\\", "/"))
    script = _img_zoom_install_script(
        f'"$(wslpath -u {windows_source})"', update=update, digest=img_zoom_digest()
    )
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
    digest = img_zoom_digest()
    if not _is_windows_host(platform):
        source = shlex.quote(IMG_ZOOM_SOURCE.as_posix())
        script = _img_zoom_install_script(source, update=update, digest=digest)
        runner.run(["sh", "-c", script], label="install img-zoom")
        return
    stage = _windows_img_zoom_stage(platform)
    stamp = stage / _IMG_ZOOM_STAMP
    if (
        runner.which("img-zoom")
        and stamp.is_file()
        and stamp.read_text(encoding="utf-8").strip() == digest
        and time.time() - stamp.stat().st_mtime < _IMG_ZOOM_REFRESH_DAYS * 86400
    ):
        runner.reporter.info("img-zoom is current")
        return
    uv = _windows_uv(runner, platform)
    _stage_img_zoom_source(runner, stage)
    upgrade = ["--upgrade"] if update else []
    runner.run([uv, "tool", "install", *upgrade, str(stage)])
    runner.write_text(stamp, digest + "\n")
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


CLI_TOOLS_SKILL = "cli-tools"
_CLI_TOOLS_LABEL = "install the basicly cli-tools skills"
_CLI_TOOLS_RECORD = "cli-tools-skill"


def _skills_user() -> list[str]:
    return ["tool", "run", "--from", harness.basicly_spec(), "basicly", "skills-user"]


def _cli_tools_current_message() -> str:
    return f"the basicly {CLI_TOOLS_SKILL} skill is current (basicly {harness.basicly_ref()})"


def _cli_tools_skills_script(*, offline: bool = False) -> str:
    spec = shlex.quote(harness.basicly_spec())
    record = f'"$HOME/.local/share/terminal-setup/{_CLI_TOOLS_RECORD}"'
    skill = f'"$HOME/.claude/skills/{CLI_TOOLS_SKILL}/SKILL.md"'
    return (
        '[ -d "$HOME/.claude" ] || { echo "Claude Code not detected ($HOME/.claude missing); '
        'skipping the cli-tools skills."; exit 0; }; '
        f'if [ -f {skill} ] && [ "$(cat {record} 2>/dev/null)" = {spec} ]; then '
        f"echo {shlex.quote(_cli_tools_current_message())}; exit 0; fi; "
        + (f"echo {shlex.quote(SKIPPED_OFFLINE)} >&2; exit 1; " if offline else "")
        + _UV_RESOLVE_POSIX
        + '"$uv" '
        + " ".join(shlex.quote(part) for part in [*_skills_user(), CLI_TOOLS_SKILL])
        + ' && mkdir -p "$HOME/.local/share/terminal-setup"'
        + f" && printf '%s\\n' {spec} > {record}"
    )


def _cli_tools_record_current(record: Path, skill: Path) -> bool:
    try:
        recorded = record.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return skill.is_file() and recorded == harness.basicly_spec()


def _deploy_cli_tools_skills_windows(runner: Runner, platform: PlatformInfo) -> None:
    if not (platform.home / ".claude").is_dir():
        runner.reporter.info(
            "Claude Code not detected (~/.claude missing); skipping the cli-tools skills."
        )
        return
    record = platform.setup_data_dir / _CLI_TOOLS_RECORD
    skill = platform.home / ".claude" / "skills" / CLI_TOOLS_SKILL / "SKILL.md"
    if _cli_tools_record_current(record, skill):
        runner.reporter.info(_cli_tools_current_message())
        return
    uv = _windows_uv(runner, platform)
    runner.run([uv, *_skills_user(), "--home", str(platform.home), CLI_TOOLS_SKILL])
    runner.write_text(record, harness.basicly_spec() + "\n")


def deploy_claude_cli_tools_skills(runner: Runner, platform: PlatformInfo) -> None:
    if not _is_windows_host(platform):
        script = _cli_tools_skills_script(offline=github_unreachable(None))
        runner.run(["sh", "-c", script], label=_CLI_TOOLS_LABEL)
        return
    distro = _wsl_distro(platform)
    offline = github_unreachable(distro)
    result = runner.run(
        wsl_exec_command(distro, ["sh", "-c", _cli_tools_skills_script(offline=offline)]),
        check=not offline,
        label=_CLI_TOOLS_LABEL,
    )
    if offline and result.returncode != 0:
        runner.failures.append(f"{_CLI_TOOLS_LABEL} in WSL")
        runner.reporter.warn(f"{_CLI_TOOLS_LABEL} in WSL failed: {SKIPPED_OFFLINE} (continuing)")
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


def _vscode_extension_installed(home: Path, extension_id: str) -> bool:
    folder = home / ".vscode" / "extensions"
    try:
        obsolete = json.loads((folder / ".obsolete").read_text(encoding="utf-8"))
    except OSError, ValueError:
        obsolete = {}
    if not isinstance(obsolete, dict):
        obsolete = {}
    pattern = re.compile(rf"{re.escape(extension_id)}-\d", re.IGNORECASE)
    try:
        entries = list(folder.iterdir())
    except OSError:
        return False
    return any(
        entry.is_dir() and pattern.match(entry.name) and entry.name not in obsolete
        for entry in entries
    )


def install_vscode_wsl_extension(runner: Runner, platform: PlatformInfo) -> None:
    if platform.os != OperatingSystem.WINDOWS:
        return
    extension_id = "ms-vscode-remote.remote-wsl"
    if _vscode_extension_installed(platform.home, extension_id):
        runner.reporter.info(f"VS Code extension {extension_id} is installed")
        return
    ensure_vscode_extension(runner, extension_id)
