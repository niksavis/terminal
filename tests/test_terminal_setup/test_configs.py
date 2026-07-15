"""Tests for configuration deployment."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from terminal_setup.configs import (
    _STARSHIP_BLOCK_MARKER,
    CHEAT_SHEET_PATH,
    TEMPLATE_DIR,
    _append_guarded_block,
    _configure_git_bash_starship,
    _configure_pwsh_starship,
    configure_vscode_terminal,
    deploy_claude_statusline,
    deploy_micro_config,
    deploy_tmux_config,
    deploy_wezterm_config,
    deploy_windows_shell_prompts,
    deploy_wsl_configs,
    deploy_zsh_config,
    template_path,
)
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo
from terminal_setup.runner import Runner


class RecordingReporter:
    """Reporter that records messages and commands for assertions."""

    def __init__(self) -> None:
        """Initialize empty record lists."""
        self.messages: list[str] = []
        self.commands: list[list[str]] = []

    def info(self, message: str) -> None:
        """Record an info message."""
        self.messages.append(message)

    def warn(self, message: str) -> None:
        """Record a warning message."""
        self.messages.append(message)

    def error(self, message: str) -> None:
        """Record an error message."""
        self.messages.append(message)

    def success(self, message: str) -> None:
        """Record a success message."""
        self.messages.append(message)

    def step(self, message: str) -> None:
        """Record a step message."""
        self.messages.append(message)

    def prompt(self, message: str) -> None:
        """Record a prompt message."""
        self.messages.append(message)

    def command(self, command: list[str]) -> None:
        """Record a command."""
        self.commands.append(command)

    def confirm(self, message: str) -> bool:
        """Return False for any confirmation prompt."""
        del message
        return False


def make_platform(
    os: OperatingSystem,
    home: Path,
    package_manager: PackageManager = PackageManager.UNKNOWN,
) -> PlatformInfo:
    """Build a PlatformInfo for testing."""
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
    """All referenced templates must exist."""
    for name in ["wezterm.lua", "tmux.conf", "zshrc", "starship.toml", "micro-settings.json"]:
        assert template_path(name).exists(), f"template {name} is missing"


def test_template_dir_exists() -> None:
    """TEMPLATE_DIR must exist and contain templates."""
    assert TEMPLATE_DIR.is_dir()
    assert len(list(TEMPLATE_DIR.iterdir())) >= 5


def test_cheat_sheet_exists() -> None:
    """The terminal cheat sheet must exist in the repo."""
    assert CHEAT_SHEET_PATH.exists(), "terminal-cheat-sheet.md should exist in repo root"


def test_deploy_wezterm_config(tmp_path: Path) -> None:
    """deploy_wezterm_config must copy the template to the config directory."""
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
    """Optional install input should be rendered into the deployed WezTerm config."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    deploy_wezterm_config(runner, platform, wsl_start_dir="$HOME/workspace")

    assert platform.wezterm_config_dir is not None
    destination = platform.wezterm_config_dir / "wezterm.lua"
    content = destination.read_text(encoding="utf-8")
    assert "$HOME/workspace" in content
    assert "__WSL_START_DIR__" not in content


def test_deploy_tmux_config(tmp_path: Path) -> None:
    """deploy_tmux_config must copy the tmux template to ~/.tmux.conf."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_tmux_config(runner, platform)

    destination = tmp_path / ".tmux.conf"
    assert destination.exists()
    assert "tmux" in destination.read_text(encoding="utf-8")


def test_deploy_zsh_config(tmp_path: Path) -> None:
    """deploy_zsh_config must copy the zsh template to ~/.zshrc."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_zsh_config(runner, platform)

    destination = tmp_path / ".zshrc"
    assert destination.exists()
    assert "HISTFILE" in destination.read_text(encoding="utf-8")


def test_deploy_micro_config(tmp_path: Path) -> None:
    """deploy_micro_config must copy micro settings to ~/.config/micro/settings.json."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    deploy_micro_config(runner, platform)

    destination = tmp_path / ".config" / "micro" / "settings.json"
    assert destination.exists()
    content = destination.read_text(encoding="utf-8")
    expected = template_path("micro-settings.json").read_text(encoding="utf-8")
    assert content == expected


def test_configure_vscode_terminal_linux(tmp_path: Path) -> None:
    """configure_vscode_terminal must set the default profile on Linux."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform)

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.defaultProfile.linux") == "zsh"


def test_configure_vscode_terminal_windows(tmp_path: Path) -> None:
    """configure_vscode_terminal must set the WSL profile on Windows."""
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
    """Windows profile should follow the detected WSL distro name."""
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
    """Stale Ubuntu profile should be removed when detected distro is Ubuntu-24.04."""
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
    """Windows settings should use an optional user-provided cwd when provided."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, windows_terminal_cwd="D:\\Workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    assert settings.get("terminal.integrated.cwd") == "D:\\Workspace"


def test_configure_vscode_terminal_windows_preserves_existing_cwd_when_unset(
    tmp_path: Path,
) -> None:
    """Without optional input, custom user cwd should be preserved."""
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
    """Without optional input, stale hardcoded cwd from older versions should be removed."""
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
    """WSL profile cwd should respect optional install input."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    configure_vscode_terminal(runner, platform, wsl_terminal_cwd="$HOME/workspace")

    assert platform.vscode_settings_path is not None
    settings = json.loads(platform.vscode_settings_path.read_text(encoding="utf-8"))
    profiles = settings.get("terminal.integrated.profiles.windows", {})
    assert profiles["Ubuntu (WSL)"]["args"] == ["-d", "Ubuntu", "--cd", "$HOME/workspace"]


def _make_claude_home(tmp_path: Path) -> Path:
    """Create a ~/.claude directory under a temp home and return it."""
    claude = tmp_path / ".claude"
    claude.mkdir(parents=True)
    return claude


def test_deploy_claude_statusline_installs(tmp_path: Path) -> None:
    """The status line script and settings.json entry must be installed."""
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
    """nerdfont=False must select the universal build via the command prefix."""
    claude = _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform, nerdfont=False)

    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == "STATUSLINE_NERDFONT=0 bash ~/.claude/statusline.sh"


def test_deploy_claude_statusline_preserves_and_is_idempotent(tmp_path: Path) -> None:
    """Existing settings keys must be preserved and repeated runs must be stable."""
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
    """Without ~/.claude the deploy must be a no-op with an info message."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    reporter = RecordingReporter()
    deploy_claude_statusline(Runner(dry_run=False, reporter=reporter), platform)

    assert not (tmp_path / ".claude").exists()
    assert any("not detected" in message for message in reporter.messages)


def test_deploy_claude_statusline_leaves_invalid_settings_unchanged(tmp_path: Path) -> None:
    """Invalid settings.json must be left untouched while the script is still copied."""
    claude = _make_claude_home(tmp_path)
    (claude / "settings.json").write_text("{not json", encoding="utf-8")
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=False), platform)

    assert (claude / "statusline.sh").exists()
    assert (claude / "settings.json").read_text(encoding="utf-8") == "{not json"


def test_deploy_claude_statusline_logs_replacement(tmp_path: Path) -> None:
    """Re-installing over an existing script must overwrite and log the replacement."""
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
    """A dry run must not write any files."""
    claude = _make_claude_home(tmp_path)
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    deploy_claude_statusline(Runner(dry_run=True), platform)

    assert not (claude / "statusline.sh").exists()
    assert not (claude / "settings.json").exists()


def test_wezterm_template_offers_git_bash() -> None:
    """The WezTerm template must add a Git Bash launch entry (auto-detected)."""
    content = template_path("wezterm.lua").read_text(encoding="utf-8")
    assert 'label = "Git Bash"' in content
    assert "find_git_bash" in content


def test_append_guarded_block_preserves_and_is_idempotent(tmp_path: Path) -> None:
    """The guarded block must preserve existing content and write at most once."""
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
    """With pwsh present the profile update command must carry the starship init."""
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
    """Without pwsh the profile must be left untouched with an info message."""
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
    """Git Bash rc files must gain a single idempotent starship block."""
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
    """Without Git Bash no rc files must be created."""
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
    """The Windows host must get its own starship.toml for the native shells."""
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    monkeypatch.setattr("terminal_setup.configs._find_git_bash", lambda _platform: None)
    runner = Runner(dry_run=False)
    monkeypatch.setattr(runner, "which", lambda _command: None)

    deploy_windows_shell_prompts(runner, platform)

    assert (tmp_path / ".config" / "starship.toml").exists()


def test_deploy_claude_statusline_windows_pushes_into_wsl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a Windows host the deploy must run the install script inside the WSL distro."""
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
    """The status line must strip CR so Windows jq's CRLF output does not break it."""
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert "tr -d '\\r'" in content


def test_statusline_template_defaults_to_universal_under_git_bash() -> None:
    """Under Git Bash (MSYS/Cygwin) the status line must default to the no-Nerd-Font build."""
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert "msys*" in content and "cygwin*" in content
    assert "NERDFONT=${STATUSLINE_NERDFONT:-0}" in content


def test_statusline_template_basenames_windows_paths() -> None:
    """The git segment must strip Windows backslash path components to show the repo name."""
    content = template_path("statusline.sh").read_text(encoding="utf-8")
    assert r"##*\\}" in content


def test_deploy_claude_statusline_windows_installs_native_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With Git Bash present the Windows-native ~/.claude must also get the status line."""
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: False)
    monkeypatch.setattr(
        "terminal_setup.configs._find_git_bash",
        lambda _platform: Path("C:/Program Files/Git/bin/bash.exe"),
    )
    claude = tmp_path / ".claude"
    claude.mkdir()
    platform = make_platform(OperatingSystem.WINDOWS, tmp_path)
    runner = Runner(dry_run=False)
    # Record the WSL push without executing wsl.exe, but let copy/write_text run.
    monkeypatch.setattr(runner, "run", lambda *a, **_k: subprocess.CompletedProcess(a, 0, "", ""))

    deploy_claude_statusline(runner, platform)

    assert (claude / "statusline.sh").exists()
    settings = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert settings["statusLine"]["command"] == "bash ~/.claude/statusline.sh"


def test_deploy_claude_statusline_windows_skips_native_without_git_bash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without Git Bash the Windows-native ~/.claude must not be configured."""
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
    """From Windows, targets must use $HOME inside the guest, never the profile name."""
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
    """Inside WSL the templates land under the real home directory."""
    platform = make_platform(OperatingSystem.LINUX, tmp_path)
    monkeypatch.setattr("terminal_setup.configs.is_running_in_wsl", lambda: True)

    deploy_wsl_configs(Runner(dry_run=False, reporter=RecordingReporter()), platform)

    assert (tmp_path / ".tmux.conf").exists()
    assert (tmp_path / ".zshrc").exists()
    assert (tmp_path / ".config" / "micro" / "settings.json").exists()
    assert (tmp_path / ".config" / "starship.toml").exists()
