from __future__ import annotations

import os
from pathlib import Path

import pytest

NETWORK_TOOLS = ("curl", "wget", "uvx", "uv")
REAL_PATH = os.environ.get("PATH", "")
GUARD_EXIT = 97
GUARD_DIR_NAME = "network-guard"


def _guard(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in NETWORK_TOOLS:
        message = f"test guard: {name} is blocked in tests; install a stub for it first"
        script = directory / name
        script.write_text(f'#!/bin/sh\necho "{message}" >&2\nexit {GUARD_EXIT}\n', encoding="utf-8")
        script.chmod(0o755)
        (directory / f"{name}.cmd").write_text(
            f"@echo off\r\necho {message} 1>&2\r\nexit /b {GUARD_EXIT}\r\n", encoding="utf-8"
        )


@pytest.fixture(autouse=True)
def block_network_tools(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    directory = tmp_path_factory.getbasetemp() / GUARD_DIR_NAME
    if not (directory / "curl").exists():
        _guard(directory)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}{os.environ.get('PATH', '')}")
    return directory


def real_tools_env() -> dict[str, str]:
    return {**os.environ, "PATH": REAL_PATH}


def guarded_system_path(*first: Path) -> str:
    guard = next(
        (
            part
            for part in os.environ.get("PATH", "").split(os.pathsep)
            if part.endswith(GUARD_DIR_NAME)
        ),
        "",
    )
    return os.pathsep.join([*(str(path) for path in first), guard, "/usr/bin", "/bin"])


@pytest.fixture(autouse=True)
def no_agent_version_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("terminal_setup.agents.latest_agent_version", lambda _agent: "")
