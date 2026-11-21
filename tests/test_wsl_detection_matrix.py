from __future__ import annotations

import importlib
from pathlib import Path

from .conftest import WSL_DETECTION_TARGETS, _host_is_wsl


def test_forced_off_wsl_detection_reaches_every_module(wsl_detection: str) -> None:
    if wsl_detection != "forced-off":
        return
    for target in WSL_DETECTION_TARGETS:
        module, _, name = target.rpartition(".")
        assert getattr(importlib.import_module(module), name)() is False


def test_a_wsl_host_runs_every_test_with_detection_forced_off(wsl_detection: str) -> None:
    assert wsl_detection in ({"host", "forced-off"} if _host_is_wsl() else {"host"})


def test_every_module_that_reads_wsl_detection_is_a_target() -> None:
    package = Path(__file__).resolve().parent.parent / "terminal_setup"
    readers = sorted(
        f"terminal_setup.{path.relative_to(package).with_suffix('').as_posix().replace('/', '.')}"
        f".is_running_in_wsl"
        for path in package.rglob("*.py")
        if "is_running_in_wsl" in path.read_text(encoding="utf-8")
    )
    assert readers == sorted(WSL_DETECTION_TARGETS)
