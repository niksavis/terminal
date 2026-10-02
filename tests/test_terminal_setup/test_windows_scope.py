from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from terminal_setup import prerequisites
from terminal_setup.prerequisites import ensure_uv_windows, is_user_scope

from .test_runner import CapturingReporter
from .test_unattended import RecordingRunner, _windows_platform

HOME = Path("C:/Users/Dev")


@pytest.mark.parametrize(
    ("path", "user"),
    [
        ("C:/Users/Dev/.local/bin/uv.exe", True),
        ("c:\\users\\dev\\AppData\\Local\\Programs\\nodejs\\node.exe", True),
        ("C:/Program Files/nodejs/node.exe", False),
        ("C:/Program Files (x86)/Python/python.exe", False),
        ("C:/ProgramData/chocolatey/bin/uv.exe", False),
        ("D:/tools/uv.exe", False),
        ("C:/Users/Other/.local/bin/uv.exe", False),
    ],
)
def test_is_user_scope_counts_only_the_user_profile(path: str, *, user: bool) -> None:
    assert is_user_scope(path, replace(_windows_platform(), home=HOME)) is user


class UvRunner(RecordingRunner):
    uv_path: str | None = None

    def which(self, command: str) -> str | None:
        return self.uv_path if command == "uv" else None


def _run_uv(uv: str | None, *, update: bool) -> UvRunner:
    runner = UvRunner(reporter=CapturingReporter())
    runner.uv_path = uv
    ensure_uv_windows(runner, replace(_windows_platform(), home=HOME), update=update)
    return runner


def test_update_never_runs_uv_self_update_under_its_own_uv() -> None:
    runner = _run_uv("C:/Users/Dev/.local/bin/uv.exe", update=True)

    assert runner.commands == []
    assert any(
        level == "info" and "install.ps1" in message and "uv self update" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_without_update_a_user_scope_uv_is_only_reported() -> None:
    runner = _run_uv("C:/Users/Dev/.local/bin/uv.exe", update=False)

    assert runner.commands == []


def test_a_machine_wide_uv_is_left_and_named() -> None:
    runner = _run_uv("C:/Program Files/uv/uv.exe", update=True)

    assert runner.commands == []
    assert any(
        level == "info" and "managed by your organisation" in message
        for level, message in runner.reporter.messages  # type: ignore[attr-defined]
    )


def test_a_missing_uv_names_the_bootstrap() -> None:
    with pytest.raises(RuntimeError, match=r"install\.ps1"):
        _run_uv(None, update=True)


def test_machine_scope_warning_names_software_center() -> None:
    reporter = CapturingReporter()
    prerequisites.report_machine_scope(
        RecordingRunner(reporter=reporter), "Node.js", "v22.3.0", "C:/x/node.exe", minimum="v26"
    )

    assert reporter.messages == [
        (
            "warn",
            "Node.js v22.3.0 at C:/x/node.exe is older than v26 and is installed machine-wide. "
            "Ask IT or use Software Center for Node.js v26 or newer; a user copy cannot "
            "override it, because Windows puts the machine PATH first.",
        )
    ]
