from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

import terminal_setup.configs as configs_module
from terminal_setup.configs import (
    _STARSHIP_BLOCK_MARKER,
    CHEAT_SHEET_PATH,
    IMG_ZOOM_SOURCE,
    TEMPLATE_DIR,
    _append_guarded_block,
    _claude_skill_wsl_install_script,
    _configure_git_bash_starship,
    _configure_pwsh_starship,
    _img_zoom_install_script,
    configure_vscode_terminal,
    deploy_all,
    deploy_claude_img_zoom_skill,
    deploy_claude_statusline,
    deploy_micro_config,
    deploy_tmux_config,
    deploy_wezterm_config,
    deploy_windows_shell_prompts,
    deploy_wsl_configs,
    deploy_zsh_config,
    install_img_zoom_native,
    install_img_zoom_wsl,
    template_path,
)
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo, wsl_exec_command
from terminal_setup.prerequisites import attempt
from terminal_setup.runner import Runner


class RecordingReporter:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.commands: list[list[str]] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warn(self, message: str) -> None:
        self.messages.append(message)

    def error(self, message: str) -> None:
        self.messages.append(message)

    def success(self, message: str) -> None:
        self.messages.append(message)

    def step(self, message: str) -> None:
        self.messages.append(message)

    def prompt(self, message: str) -> None:
        self.messages.append(message)

    def command(self, command: list[str]) -> None:
        self.commands.append(command)

    def confirm(self, message: str) -> bool:
        del message
        return False


def make_platform(
    os: OperatingSystem,
    home: Path,
    package_manager: PackageManager = PackageManager.UNKNOWN,
) -> PlatformInfo:
    return PlatformInfo(
        os=os,
        package_manager=package_manager,
        is_wsl_available=False,
        is_wsl_default_ubuntu=False,
        wsl_distribution="Ubuntu" if os == OperatingSystem.WINDOWS else None,
        shell="/bin/zsh",
        home=home,
        wezterm_config_dir=home / ".config" / "wezterm",
        vscode_settings_path=home / "settings.json",
    )


def test_template_path_points_to_existing_files() -> None:
    for name in ["wezterm.lua", "tmux.conf", "zshrc", "starship.toml", "micro-settings.json"]:
        assert template_path(name).exists(), f"template {name} is missing"


def test_template_dir_exists() -> None:
    assert TEMPLATE_DIR.is_dir()
    assert len(list(TEMPLATE_DIR.iterdir())) >= 5


def test_cheat_sheet_exists() -> None:
    assert CHEAT_SHEET_PATH.exists(), "terminal-cheat-sheet.md should exist in repo root"


def test_deploy_wezterm_config(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_wezterm_config(runner, platform)

    assert platform.wezterm_config_dir is not None
    destination = platform.wezterm_config_dir / "wezterm.lua"
    assert destination.exists()
    content = destination.read_text(encoding="utf-8")
    assert "WezTerm" in content
    assert "__WSL_START_DIR__" not in content


def test_deploy_wezterm_config_supports_optional_wsl_start_dir(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    deploy_wezterm_config(runner, platform, wsl_start_dir="$HOME/workspace")

    assert platform.wezterm_config_dir is not None
    destination = platform.wezterm_config_dir / "wezterm.lua"
    content = destination.read_text(encoding="utf-8")
    assert "$HOME/workspace" in content
    assert "__WSL_START_DIR__" not in content


def test_deploy_tmux_config(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_tmux_config(runner, platform)

    destination = tmp_path / ".tmux.conf"
    assert destination.exists()
    assert "tmux" in destination.read_text(encoding="utf-8")


def test_deploy_zsh_config(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_zsh_config(runner, platform)

    destination = tmp_path / ".zshrc"
    assert destination.exists()
    assert "HISTFILE" in destination.read_text(encoding="utf-8")


def test_deploy_micro_config(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_micro_config(runner, platform)

    destination = tmp_path / ".config" / "micro" / "settings.json"
    assert destination.exists()
    content = destination.read_text(encoding="utf-8")
    expected = template_path("micro-settings.json").read_text(encoding="utf-8")
    assert content == expected


def test_configure_vscode_terminal_linux(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.linux") == "zsh"


def test_configure_vscode_terminal_windows(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.windows") == "Ubuntu (WSL)"
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "Ubuntu (WSL)" in profiles
    assert profiles["Ubuntu (WSL)"]["args"] == ["-d", "Ubuntu"]


def test_configure_vscode_terminal_windows_uses_detected_distro(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    platform = PlatformInfo(
        os=platform.os,
        package_manager=platform.package_manager,
        is_wsl_available=platform.is_wsl_available,
        is_wsl_default_ubuntu=platform.is_wsl_default_ubuntu,
        wsl_distribution="Ubuntu-24.04",
        shell=platform.shell,
        home=platform.home,
        wezterm_config_dir=platform.wezterm_config_dir,
        vscode_settings_path=platform.vscode_settings_path,
    )
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.windows") == "Ubuntu-24.04 (WSL)"
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "Ubuntu-24.04 (WSL)" in profiles
    assert profiles["Ubuntu-24.04 (WSL)"]["args"] == ["-d", "Ubuntu-24.04"]
    assert "Ubuntu (WSL)" not in profiles


def test_configure_vscode_terminal_windows_removes_stale_ubuntu_profile(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    platform = PlatformInfo(
        os=platform.os,
        package_manager=platform.package_manager,
        is_wsl_available=platform.is_wsl_available,
        is_wsl_default_ubuntu=platform.is_wsl_default_ubuntu,
        wsl_distribution="Ubuntu-24.04",
        shell=platform.shell,
        home=platform.home,
        wezterm_config_dir=platform.wezterm_config_dir,
        vscode_settings_path=platform.vscode_settings_path,
    )
    assert platform.vscode_settings_path is not None
    stale = {
        "terminal.integrated.profiles.windows": {
            "WSL (Default)": {
                "path": "C:\\Windows\\System32\\wsl.exe",
                "icon": "terminal-ubuntu",
            },
            "Ubuntu (WSL)": {
                "path": "C:\\Windows\\System32\\wsl.exe",
                "args": ["-d", "Ubuntu"],
                "icon": "terminal-ubuntu",
            },
        }
    }
    platform.vscode_settings_path.write_text(json.dumps(stale, indent=2) + "\n", encoding="utf-8")

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert "WSL (Default)" not in profiles
    assert "Ubuntu (WSL)" not in profiles
    assert "Ubuntu-24.04 (WSL)" in profiles


def test_configure_vscode_terminal_windows_sets_optional_cwd(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, windows_terminal_cwd="D:\\Workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.cwd") == "D:\\Workspace"


def test_configure_vscode_terminal_windows_preserves_existing_cwd_when_unset(
    tmp_path: Path,
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    assert platform.vscode_settings_path is not None
    platform.vscode_settings_path.write_text(
        json.dumps({"terminal.integrated.cwd": "E:\\Workspace"}, indent=2) + "\n",
        encoding="utf-8",
    )

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.cwd") == "E:\\Workspace"


def test_configure_vscode_terminal_windows_removes_stale_existing_cwd_when_unset(
    tmp_path: Path,
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    assert platform.vscode_settings_path is not None
    platform.vscode_settings_path.write_text(
        json.dumps({"terminal.integrated.cwd": "D:\\Development"}, indent=2) + "\n",
        encoding="utf-8",
    )

    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert "terminal.integrated.cwd" not in settings


def test_configure_vscode_terminal_windows_uses_optional_wsl_cwd(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, wsl_terminal_cwd="$HOME/workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert profiles["Ubuntu (WSL)"]["args"] == ["-d", "Ubuntu", "--cd", "$HOME/workspace"]


def _make_claude_home(tmp_path: Path) -> Path:
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    return claude


def test_deploy_claude_statusline_installs(tmp_path: Path) -> None:
    claude = _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform)

    script = claude / "statusline.sh"
    assert script.exists()
    assert "Claude Code status line" in script.read_text(encoding="utf-8")
    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"] == {
        "type": "command",
        "command": "bash ~/.claude/statusline.sh",
        "padding": 0,
    }


def test_deploy_claude_statusline_universal_font(tmp_path: Path) -> None:
    claude = _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform, nerdfont=False)

    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == "STATUSLINE_NERDFONT=0 bash ~/.claude/statusline.sh"


def test_deploy_claude_statusline_preserves_and_is_idempotent(tmp_path: Path) -> None:
    claude = _make_claude_home(tmp_path)
    (claude / "settings.json").write_text(
        json.dumps({"theme": "dark"}, indent=2) + "\n", encoding="utf-8"
    )
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform)
    deploy_claude_statusline(Runner(dry_run=False), platform)

    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["theme"] == "dark"
    assert settings["statusLine"]["command"] == "bash ~/.claude/statusline.sh"


def test_deploy_claude_statusline_skips_without_claude_dir(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    reporter = RecordingReporter()
    deploy_claude_statusline(Runner(dry_run=False, reporter=reporter), platform)

    assert not (tmp_path / ".claude").exists()
    assert any("not detected" in message for message in reporter.messages)


def test_deploy_claude_statusline_leaves_invalid_settings_unchanged(tmp_path: Path) -> None:
    claude = _make_claude_home(tmp_path)
    (claude / "settings.json").write_text("{not json", encoding="utf-8")
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform)

    assert (claude / "statusline.sh").exists()
    assert (claude / "settings.json").read_text(encoding="utf-8") == "{not json"


def test_deploy_claude_statusline_logs_replacement(tmp_path: Path) -> None:
    _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform)

    reporter = RecordingReporter()
    deploy_claude_statusline(Runner(dry_run=False, reporter=reporter), platform)
    assert any(
        "Replacing existing" in message and "statusline.sh" in message
        for message in reporter.messages
    )


def test_deploy_claude_statusline_dry_run_makes_no_changes(tmp_path: Path) -> None:
    claude = _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=True), platform)

    assert not (claude / "statusline.sh").exists()
    assert not (claude / "settings.json").exists()


def test_wezterm_template_offers_git_bash() -> None:
    content = template_path("wezterm.lua").read_text(encoding="utf-8")
    assert 'label = "Git Bash"' in content
    assert "find_git_bash" in content


@pytest.mark.parametrize("label", ["PowerShell", "Git Bash", "Command Prompt"])
def test_wezterm_windows_launch_entries_pin_local_domain(label: str) -> None:

    content = template_path("wezterm.lua").read_text(encoding="utf-8")
    assert 'local local_domain = { DomainName = "local" }' in content
    entry = re.search(rf'label = "{re.escape(label)}",\s*\n\s*domain = local_domain,', content)
    assert entry is not None, f"{label} launch entry does not pin the local domain"


def test_wezterm_open_config_pins_local_domain() -> None:
    content = template_path("wezterm.lua").read_text(encoding="utf-8")
    action = re.search(r'domain = local_domain,\s*\n\s*args = \{ "notepad\.exe"', content)
    assert action is not None, "notepad.exe action does not pin the local domain"


def test_wezterm_wsl_launch_entry_pins_wsl_domain() -> None:
    content = template_path("wezterm.lua").read_text(encoding="utf-8")
    entry = re.search(
        r'label = "Ubuntu \(WSL\)",\s*\n\s*domain = \{ DomainName = wsl_default_domain \},',
        content,
    )
    assert entry is not None, "WSL launch entry does not pin the WSL domain"


def test_append_guarded_block_preserves_and_is_idempotent(tmp_path: Path) -> None:
    rc = tmp_path / "rc"
    rc.write_text("existing line\n", encoding="utf-8")
    runner = Runner(dry_run=False)

    assert _append_guarded_block(runner, rc, "# marker", "# marker\nblock\n") is True
    assert _append_guarded_block(runner, rc, "# marker", "# marker\nblock\n") is False

    content = rc.read_text(encoding="utf-8")
    assert content.startswith("existing line\n")
    assert content.count("# marker") == 1
    assert "block" in content


def test_configure_pwsh_starship_appends_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    reporter = RecordingReporter()
    runner = Runner(dry_run=True, reporter=reporter)
    monkeypatch.setattr(runner, "which", lambda _command: "C:/pwsh.exe")

    _configure_pwsh_starship(runner, platform)

    joined = [" ".join(command) for command in reporter.commands]
    assert any(
        "pwsh" in command
        and "starship init powershell" in command
        and _STARSHIP_BLOCK_MARKER in command
        for command in joined
    )


def test_configure_pwsh_starship_skips_without_pwsh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    reporter = RecordingReporter()
    runner = Runner(dry_run=True, reporter=reporter)
    monkeypatch.setattr(runner, "which", lambda _command: None)

    _configure_pwsh_starship(runner, platform)

    assert reporter.commands == []
    assert any("PowerShell 7" in message for message in reporter.messages)


def test_configure_git_bash_starship_writes_rc_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    monkeypatch.setattr(
        "terminal_setup.configs._find_git_bash",
        lambda _platform: Path("C:/Program Files/Git/bin/bash.exe"),
    )
    runner = Runner(dry_run=False)

    _configure_git_bash_starship(runner, platform)
    _configure_git_bash_starship(runner, platform)

    bashrc = (tmp_path / ".bashrc").read_text(encoding="utf-8")
    assert bashrc.count(_STARSHIP_BLOCK_MARKER) == 1
    assert "starship init bash" in bashrc
    bash_profile = (tmp_path / ".bash_profile").read_text(encoding="utf-8")
    assert ".bashrc" in bash_profile


def test_configure_git_bash_starship_skips_without_git_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    monkeypatch.setattr("terminal_setup.configs._find_git_bash", lambda _platform: None)
    reporter = RecordingReporter()
    runner = Runner(dry_run=False, reporter=reporter)

    _configure_git_bash_starship(runner, platform)

    assert not (tmp_path / ".bashrc").exists()
    assert not (tmp_path / ".bash_profile").exists()
    assert any("Git Bash not found" in message for message in reporter.messages)


def test_deploy_windows_shell_prompts_deploys_host_starship(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    monkeypatch.setattr("terminal_setup.configs._find_git_bash", lambda _platform: None)
    runner = Runner(dry_run=False)
    monkeypatch.setattr(runner, "which", lambda _command: None)

    deploy_windows_shell_prompts(runner, platform)

    assert (tmp_path / ".config" / "starship.toml").exists()


def test_deploy_claude_statusline_windows_pushes_into_wsl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    reporter = RecordingReporter()
    deploy_claude_statusline(Runner(dry_run=True, reporter=reporter), platform)

    joined = [" ".join(command) for command in reporter.commands]
    assert any(
        "statusline.sh" in command and "jq" in command and "$HOME/.claude" in command
        for command in joined
    )


def test_statusline_template_strips_cr_from_jq() -> None:
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert "tr -d '\\r'" in content


def test_statusline_template_defaults_to_universal_under_git_bash() -> None:
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert "msys*" in content and "cygwin*" in content
    assert "NERDFONT=${STATUSLINE_NERDFONT:-0}" in content


def test_statusline_template_basenames_windows_paths() -> None:
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert r"##*\\}" in content


def test_deploy_claude_statusline_windows_installs_native_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setattr(
        "terminal_setup.configs._find_git_bash",
        lambda _platform: Path("C:/Program Files/Git/bin/bash.exe"),
    )
    claude = tmp_path / ".claude"
    claude.mkdir()
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    monkeypatch.setattr(runner, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 0, "", ""))

    deploy_claude_statusline(runner, platform)

    assert (claude / "statusline.sh").exists()
    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == "bash ~/.claude/statusline.sh"


def test_deploy_claude_statusline_windows_skips_native_without_git_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setattr("terminal_setup.configs._find_git_bash", lambda _platform: None)
    claude = tmp_path / ".claude"
    claude.mkdir()
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    monkeypatch.setattr(runner, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 0, "", ""))

    deploy_claude_statusline(runner, platform)

    assert not (claude / "statusline.sh").exists()
    assert not (claude / "settings.json").exists()


def test_deploy_wsl_configs_resolves_guest_home_not_windows_username(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "WinUser"
    home.mkdir()
    platform = make_platform(OperatingSystem.WINDOWS, home)
    runner = Runner(dry_run=False, reporter=RecordingReporter())
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setattr(
        "terminal_setup.configs._to_wsl_path",
        lambda _runner, _distro, source: f"/mnt/c/templates/{source.name}",
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(
        runner,
        "run",
        lambda command, **_kwargs: (
            commands.append(command) or subprocess.CompletedProcess(command, 0, "", "")
        ),
    )

    deploy_wsl_configs(runner, platform)

    assert commands, "expected wsl deploy commands"
    for command in commands:
        script = command[-1]
        assert command[-3:-1] == ["sh", "-c"]
        assert "$HOME/" in script
        assert "WinUser" not in script
    scripts = [command[-1] for command in commands]
    assert any('mkdir -p "$HOME/.config/micro"' in script for script in scripts)
    assert any('"$HOME/.tmux.conf"' in script for script in scripts)


def test_deploy_wsl_configs_inside_wsl_uses_platform_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: True)

    deploy_wsl_configs(Runner(dry_run=False, reporter=RecordingReporter()), platform)

    assert (tmp_path / ".tmux.conf").exists()
    assert (tmp_path / ".zshrc").exists()
    assert (tmp_path / ".config" / "micro" / "settings.json").exists()
    assert (tmp_path / ".config" / "starship.toml").exists()


def test_wsl_start_dir_rejects_shell_metacharacters(tmp_path: Path) -> None:
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False, reporter=RecordingReporter())
    for bad in ['"broken"', "a`whoami`", "$(rm -rf /)", "back\\slash"]:
        with pytest.raises(ValueError, match="wsl-terminal-cwd"):
            deploy_wezterm_config(runner, platform, wsl_start_dir=bad)
    deploy_wezterm_config(runner, platform, wsl_start_dir="$HOME/workspace")
    assert platform.wezterm_config_dir is not None
    rendered = (platform.wezterm_config_dir / "wezterm.lua").read_text(encoding="utf-8")
    assert 'cd "$HOME/workspace"' in rendered


def _posix_only(test: object) -> object:
    return pytest.mark.skipif(
        sys.platform == "win32", reason="the script runs in a POSIX sh inside WSL or on a Unix host"
    )(test)


class _FakeRun:
    def __init__(self, bin_dir: str = "") -> None:
        self.commands: list[list[str]] = []
        self.bin_dir = bin_dir

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        stdout = self.bin_dir if command[1:] == ["tool", "dir", "--bin"] else ""
        return subprocess.CompletedProcess(command, 0, stdout, "")


def test_img_zoom_source_ships_inside_the_package() -> None:
    assert IMG_ZOOM_SOURCE.parent == Path(configs_module.__file__).resolve().parent
    assert (IMG_ZOOM_SOURCE / "pyproject.toml").is_file()


def test_package_data_names_every_img_zoom_source_file() -> None:
    root = Path(__file__).resolve().parents[2]
    patterns = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "setuptools"
    ]["package-data"]["terminal_setup"]
    package = root / "terminal_setup"
    shipped = [
        path
        for path in IMG_ZOOM_SOURCE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]

    assert len(shipped) == 5
    for path in shipped:
        relative = PurePosixPath(path.relative_to(package).as_posix())
        assert any(relative.full_match(pattern) for pattern in patterns), relative


def test_img_zoom_leaves_out_opencv_only_on_windows_arm64() -> None:
    project = tomllib.loads((IMG_ZOOM_SOURCE / "pyproject.toml").read_text(encoding="utf-8"))
    opencv = next(dep for dep in project["project"]["dependencies"] if "opencv" in dep)

    assert opencv.startswith("opencv-python-headless>=5;")
    assert "sys_platform != 'win32' or platform_machine != 'ARM64'" in opencv


def test_install_img_zoom_native_posix_runs_uv_tool_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    reporter = RecordingReporter()
    install_img_zoom_native(
        Runner(dry_run=True, reporter=reporter), make_platform(OperatingSystem.LINUX, tmp_path)
    )

    script = reporter.commands[-1][-1]
    assert f"tool install {IMG_ZOOM_SOURCE.as_posix()}" in script
    assert "--upgrade" not in script


def test_install_img_zoom_native_upgrades_on_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    reporter = RecordingReporter()
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    install_img_zoom_native(Runner(dry_run=True, reporter=reporter), platform, update=True)

    assert "tool install --upgrade " in reporter.commands[-1][-1]


def test_install_img_zoom_wsl_installs_inside_wsl_from_the_mounted_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setattr(
        "terminal_setup.configs.IMG_ZOOM_SOURCE",
        PureWindowsPath("C:/src/terminal/terminal_setup/img_zoom_tool"),
    )
    reporter = RecordingReporter()
    install_img_zoom_wsl(
        Runner(dry_run=True, reporter=reporter), make_platform(OperatingSystem.WINDOWS, tmp_path)
    )

    command = reporter.commands[-1]
    assert command[:-1] == wsl_exec_command("Ubuntu", ["sh", "-c"])
    assert "tool install /mnt/c/src/terminal/terminal_setup/img_zoom_tool" in command[-1]


@pytest.mark.parametrize("update", [False, True])
def test_install_img_zoom_native_windows_uses_the_uv_running_setup_and_adds_its_bin_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, update: bool
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setenv("UV", "C:/Users/u/.local/bin/uv.exe")
    added: list[Path] = []
    monkeypatch.setattr(
        "terminal_setup.configs._add_to_user_path", lambda _runner, path: added.append(path)
    )
    runner = Runner(dry_run=False, reporter=RecordingReporter())
    fake = _FakeRun(bin_dir="C:/Users/u/.local/bin\n")
    monkeypatch.setattr(runner, "run", fake)

    install_img_zoom_native(runner, make_platform(OperatingSystem.WINDOWS, tmp_path), update=update)

    upgrade = ["--upgrade"] if update else []
    assert fake.commands == [
        ["C:/Users/u/.local/bin/uv.exe", "tool", "install", *upgrade, str(IMG_ZOOM_SOURCE)],
        ["C:/Users/u/.local/bin/uv.exe", "tool", "dir", "--bin"],
    ]
    assert added == [Path("C:/Users/u/.local/bin")]


def test_install_img_zoom_native_windows_without_uv_fails_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.delenv("UV", raising=False)
    runner = Runner(dry_run=False, reporter=RecordingReporter())
    monkeypatch.setattr(runner, "which", lambda _command: None)
    fake = _FakeRun()
    monkeypatch.setattr(runner, "run", fake)
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)

    ok = attempt(runner, "install img-zoom", lambda: install_img_zoom_native(runner, platform))

    assert ok is False
    assert runner.failures == ["install img-zoom"]
    assert fake.commands == []


def _run_install_script(
    tmp_path: Path, *, uv_in_local_bin: bool, uv_env: bool = False
) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    bin_dir = home / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin"}
    for name, wanted, directory in (
        ("uv", uv_in_local_bin, bin_dir),
        ("uv-from-env", uv_env, tmp_path),
    ):
        if wanted:
            fake_uv = directory / name
            fake_uv.write_text(
                f'#!/bin/sh\necho "{name} $@" > {tmp_path / "uv-args"}\n', encoding="utf-8"
            )
            fake_uv.chmod(0o755)
    if uv_env:
        env["UV"] = str(tmp_path / "uv-from-env")
    script = _img_zoom_install_script("/pkg/img_zoom_tool", update=False)
    return subprocess.run(
        ["/bin/sh", "-c", script], env=env, capture_output=True, text=True, check=False
    )


@_posix_only
def test_install_script_finds_uv_in_local_bin_when_path_lacks_it(tmp_path: Path) -> None:
    result = _run_install_script(tmp_path, uv_in_local_bin=True)

    assert result.returncode == 0, result.stderr
    recorded = (tmp_path / "uv-args").read_text(encoding="utf-8").strip()
    assert recorded == "uv tool install /pkg/img_zoom_tool"


@_posix_only
def test_install_script_prefers_the_uv_named_by_uv_env(tmp_path: Path) -> None:
    result = _run_install_script(tmp_path, uv_in_local_bin=True, uv_env=True)

    assert result.returncode == 0, result.stderr
    recorded = (tmp_path / "uv-args").read_text(encoding="utf-8").strip()
    assert recorded == "uv-from-env tool install /pkg/img_zoom_tool"


@_posix_only
def test_install_script_refuses_by_name_when_uv_is_missing(tmp_path: Path) -> None:
    result = _run_install_script(tmp_path, uv_in_local_bin=False)

    assert result.returncode == 1
    assert "uv not found in PATH or ~/.local/bin" in result.stderr


def _home_with_img_zoom(tmp_path: Path, executable: str = "img-zoom") -> Path:
    claude = _make_claude_home(tmp_path)
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / executable).write_text("", encoding="utf-8")
    return claude


def test_deploy_claude_img_zoom_skill_writes_the_user_skill_when_img_zoom_is_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = _home_with_img_zoom(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    monkeypatch.setattr(runner, "which", lambda _command: None)
    deploy_claude_img_zoom_skill(runner, platform)
    deploy_claude_img_zoom_skill(runner, platform)

    skill = claude / "skills" / "img-zoom" / "SKILL.md"
    assert skill.read_text(encoding="utf-8") == template_path("img-zoom-skill.md").read_text(
        encoding="utf-8"
    )
    assert [path.name for path in (claude / "skills").iterdir()] == ["img-zoom"]


def test_deploy_claude_img_zoom_skill_skips_when_img_zoom_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claude = _make_claude_home(tmp_path)
    reporter = RecordingReporter()
    runner = Runner(dry_run=False, reporter=reporter)
    monkeypatch.setattr(runner, "which", lambda _command: None)
    deploy_claude_img_zoom_skill(runner, make_platform(OperatingSystem.LINUX, tmp_path))

    assert not (claude / "skills").exists()
    assert any("img-zoom is not installed here" in message for message in reporter.messages)


def test_deploy_claude_img_zoom_skill_skips_without_claude_dir(tmp_path: Path) -> None:
    reporter = RecordingReporter()
    deploy_claude_img_zoom_skill(
        Runner(dry_run=False, reporter=reporter), make_platform(OperatingSystem.LINUX, tmp_path)
    )

    assert not (tmp_path / ".claude").exists()
    assert any("skipping the img-zoom skill" in message for message in reporter.messages)


def test_deploy_claude_img_zoom_skill_windows_writes_both_sides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    claude = _home_with_img_zoom(tmp_path, "img-zoom.exe")
    reporter = RecordingReporter()
    runner = Runner(dry_run=False, reporter=reporter)
    fake = _FakeRun()
    monkeypatch.setattr(runner, "run", fake)
    monkeypatch.setattr(runner, "which", lambda _command: None)
    monkeypatch.setattr("terminal_setup.configs._to_wsl_path", lambda *_a: "/mnt/c/skill.md")

    deploy_claude_img_zoom_skill(runner, make_platform(OperatingSystem.WINDOWS, tmp_path))

    assert fake.commands[0][:-1] == wsl_exec_command("Ubuntu", ["sh", "-c"])
    assert "/mnt/c/skill.md" in fake.commands[0][-1]
    assert (claude / "skills" / "img-zoom" / "SKILL.md").is_file()


def _run_skill_script(tmp_path: Path, *, installed: bool) -> Path:
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    if installed:
        local_bin = home / ".local" / "bin"
        local_bin.mkdir(parents=True)
        tool = local_bin / "img-zoom"
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)
    source = tmp_path / "SKILL.md"
    source.write_text("skill", encoding="utf-8")
    subprocess.run(
        ["/bin/sh", "-c", _claude_skill_wsl_install_script(str(source), "img-zoom")],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    return home / ".claude" / "skills" / "img-zoom" / "SKILL.md"


@_posix_only
def test_wsl_skill_script_writes_the_skill_when_img_zoom_is_installed(tmp_path: Path) -> None:
    assert _run_skill_script(tmp_path, installed=True).read_text(encoding="utf-8") == "skill"


@_posix_only
def test_wsl_skill_script_skips_when_img_zoom_is_missing(tmp_path: Path) -> None:
    assert not _run_skill_script(tmp_path, installed=False).exists()


def test_img_zoom_skill_is_model_invocable_and_names_the_portable_python() -> None:
    content = template_path("img-zoom-skill.md").read_text(encoding="utf-8")
    front_matter = content.split("---")[1]

    assert "name: img-zoom" in front_matter
    assert "description: " in front_matter
    assert "disable-model-invocation" not in front_matter
    assert '"$(img-zoom --python)"' in content
    assert "bin/python" not in content


@pytest.mark.parametrize("include_claude", [True, False])
def test_deploy_all_writes_the_skill_only_with_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, include_claude: bool
) -> None:
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    claude = _home_with_img_zoom(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False, reporter=RecordingReporter())
    monkeypatch.setattr(runner, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 0, "", ""))
    monkeypatch.setattr(runner, "which", lambda _command: None)
    deploy_all(
        runner, platform, include_starship=False, include_claude=include_claude, no_sudo=True
    )

    assert (claude / "skills" / "img-zoom" / "SKILL.md").exists() is include_claude
