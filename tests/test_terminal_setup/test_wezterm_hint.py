from __future__ import annotations

from dataclasses import replace

import pytest

from terminal_setup import prerequisites
from terminal_setup.platform import OperatingSystem

from .test_unattended import _windows_platform


def test_the_start_command_is_a_quoted_powershell_call_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prerequisites, "is_running_in_wsl", lambda: False)
    path = "C:/Users/Ann O'Neil/AppData/Local/Programs/WezTerm/wezterm-gui.exe"

    hint = prerequisites.wezterm_start_hint(_windows_platform(), path)

    assert hint.endswith("& 'C:/Users/Ann O''Neil/AppData/Local/Programs/WezTerm/wezterm-gui.exe'")
    assert "Windows Terminal or PowerShell" in hint


def test_the_hint_names_the_path_outside_windows() -> None:
    linux = replace(_windows_platform(), os=OperatingSystem.LINUX)

    hint = prerequisites.wezterm_start_hint(linux, "/home/u/.local/bin/wezterm")

    assert hint == "WezTerm is installed at /home/u/.local/bin/wezterm"
