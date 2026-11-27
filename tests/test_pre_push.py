from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".scripts" / "git-hooks" / "pre-push.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pre_push_hook", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pre_push = _load()


def _record_runs(monkeypatch: pytest.MonkeyPatch, code: int = 0) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return type("Done", (), {"returncode": code})()

    monkeypatch.setattr(pre_push.subprocess, "run", fake_run)
    return calls


@pytest.mark.parametrize(
    ("value", "ci"), [("true", True), ("1", True), ("", False), ("false", False), ("0", False)]
)
def test_ci_is_read_from_the_environment(value: str, ci: bool) -> None:
    assert pre_push.in_ci({"CI": value}) is ci


def test_a_local_push_runs_only_the_bundle_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    calls = _record_runs(monkeypatch)

    assert pre_push.main() == 0
    assert calls == [["uv", "run", "python", ".scripts/bundle_cli_tools_skill.py", "--check"]]
    assert "no tests run here" in capsys.readouterr().out


def test_ci_runs_the_bundle_check_and_the_whole_suite(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CI", "true")
    calls = _record_runs(monkeypatch)

    assert pre_push.main() == 0
    assert calls == [
        ["uv", "run", "python", ".scripts/bundle_cli_tools_skill.py", "--check"],
        ["uv", "run", "pytest", "tests/"],
    ]
    assert "pre-push passed in CI: bundle check, pytest" in capsys.readouterr().out


@pytest.mark.parametrize("ci", ["", "true"])
def test_a_failed_bundle_check_stops_the_push_before_pytest(
    monkeypatch: pytest.MonkeyPatch, ci: str
) -> None:
    monkeypatch.setenv("CI", ci)
    calls = _record_runs(monkeypatch, code=1)

    assert pre_push.main() == 1
    assert len(calls) == 1


def test_ci_fails_when_pytest_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(pre_push, "_bundle_check", lambda: 0)
    monkeypatch.setattr(pre_push, "_pytest", lambda: 1)

    assert pre_push.main() == 1


def test_pyright_and_bandit_run_only_in_the_full_mode() -> None:
    checks = tomllib.loads((ROOT / "basicly.toml").read_text(encoding="utf-8"))["verify"]["checks"]
    modes = {check["name"]: check["modes"] for check in checks}

    assert modes["pyright"] == ["full"]
    assert modes["bandit"] == ["full"]
    assert modes["pytest"] == ["full"]
    assert modes["ruff"] == ["fast", "full"]
    assert modes["ruff-format"] == ["fast", "full"]
