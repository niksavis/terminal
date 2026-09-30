from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from terminal_setup.platform import (
    OperatingSystem,
    PackageManager,
    detect_os,
    detect_package_manager,
    get_home_directory,
    get_vscode_settings_path,
    is_debian_family,
    is_running_in_wsl,
    os_release_ids,
    read_os_release,
)

UBUNTU_2404_OS_RELEASE = """PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo
"""


def test_detect_os_returns_known_value() -> None:
    os = detect_os()
    assert os in OperatingSystem


def test_detect_package_manager_matches_os() -> None:
    os = detect_os()
    manager = detect_package_manager(os)
    assert manager in PackageManager


def test_home_directory_exists() -> None:
    home = get_home_directory()
    assert home.exists()
    assert home.is_dir()


def test_is_running_in_wsl_true_for_microsoft_kernel() -> None:
    with (
        mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.LINUX),
        mock.patch(
            "pathlib.Path.read_text",
            return_value="5.15.146.1-microsoft-standard-WSL2",
        ),
    ):
        assert is_running_in_wsl() is True


def test_is_running_in_wsl_false_on_non_linux() -> None:
    with mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.WINDOWS):
        assert is_running_in_wsl() is False


def test_is_running_in_wsl_false_for_plain_linux() -> None:
    with (
        mock.patch("terminal_setup.platform.detect_os", return_value=OperatingSystem.LINUX),
        mock.patch("pathlib.Path.read_text", return_value="6.8.0-35-generic"),
    ):
        assert is_running_in_wsl() is False


def test_vscode_settings_fallback_is_a_real_user_settings_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("terminal_setup.platform.get_home_directory", lambda: tmp_path)
    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.LINUX)
    path = get_vscode_settings_path()
    assert path == tmp_path / ".config" / "Code" / "User" / "settings.json"

    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.WINDOWS)
    path = get_vscode_settings_path()
    assert path == tmp_path / "AppData" / "Roaming" / "Code" / "User" / "settings.json"


def test_vscode_settings_prefers_existing_location(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    existing = tmp_path / ".config" / "Code" / "User" / "settings.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("terminal_setup.platform.get_home_directory", lambda: tmp_path)
    monkeypatch.setattr("terminal_setup.platform.detect_os", lambda: OperatingSystem.WINDOWS)
    assert get_vscode_settings_path() == existing


@pytest.mark.parametrize(
    ("text", "ids", "debian_family"),
    [
        (UBUNTU_2404_OS_RELEASE, ("ubuntu", "debian"), True),
        ('PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\n', ("debian",), True),
        ("ID=kali\nID_LIKE=debian\n", ("kali", "debian"), True),
        ('ID="pengwin"\nID_LIKE="debian"\n', ("pengwin", "debian"), True),
        ('NAME="Fedora Linux"\nID=fedora\n', ("fedora",), False),
        ('NAME="Arch Linux"\nID=arch\n', ("arch",), False),
        (
            'ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n',
            ("opensuse-tumbleweed", "opensuse", "suse"),
            False,
        ),
        ("ID=Ubuntu\n", ("ubuntu",), True),
        ("", (), False),
        ("ID_LIKE=debian\n", (), False),
    ],
)
def test_os_release_family_is_read_from_id_and_id_like(
    text: str, ids: tuple[str, ...], debian_family: bool
) -> None:
    assert os_release_ids(text) == ids
    assert is_debian_family(os_release_ids(text)) is debian_family


def test_read_os_release_asks_the_named_distro_through_wsl_exec() -> None:
    completed = mock.Mock(returncode=0, stdout=UBUNTU_2404_OS_RELEASE)
    with mock.patch("terminal_setup.platform.subprocess.run", return_value=completed) as run:
        assert read_os_release("Debian") == UBUNTU_2404_OS_RELEASE
    assert run.call_args.args[0] == ["wsl", "-d", "Debian", "--exec", "cat", "/etc/os-release"]


def test_read_os_release_is_empty_when_the_distro_does_not_answer() -> None:
    completed = mock.Mock(returncode=1, stdout="partial")
    with mock.patch("terminal_setup.platform.subprocess.run", return_value=completed):
        assert read_os_release("Gone") == ""
    with mock.patch("terminal_setup.platform.subprocess.run", side_effect=OSError):
        assert read_os_release("Gone") == ""
