from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".scripts" / "git-hooks" / "pre-push.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pre_push_hook", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pre_push = _load()

TESTS = {
    Path("tests/test_terminal_setup/test_configs.py"): (
        "from terminal_setup.configs import deploy_all\nfrom terminal_setup import harness\n"
    ),
    Path(
        "tests/test_terminal_setup/test_cli.py"
    ): "from terminal_setup import (\n    cli,\n    runner,\n)\n",
    Path(
        "tests/test_render_cheat_sheet.py"
    ): 'SCRIPT = ROOT / ".scripts" / "render-cheat-sheet.py"\n',
    Path("tests/test_readme.py"): 'README = ROOT / "README.md"\n',
}


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        (
            ["terminal_setup/configs.py"],
            {"tests/test_terminal_setup/test_configs.py": "uses terminal_setup/configs.py"},
        ),
        (
            ["terminal_setup/runner.py"],
            {"tests/test_terminal_setup/test_cli.py": "uses terminal_setup/runner.py"},
        ),
        (
            ["terminal_setup/harness.py"],
            {"tests/test_terminal_setup/test_configs.py": "uses terminal_setup/harness.py"},
        ),
        (
            [".scripts/render-cheat-sheet.py"],
            {"tests/test_render_cheat_sheet.py": "uses .scripts/render-cheat-sheet.py"},
        ),
        (["README.md"], {"tests/test_readme.py": "uses README.md"}),
        (["tests/test_readme.py", "README.md"], {"tests/test_readme.py": "changed"}),
        (["pyproject.toml", "tests/conftest.py", "docs/releases.md"], {}),
        (["tests/test_gone.py"], {}),
    ],
)
def test_local_pre_push_selects_the_tests_of_the_changed_files(
    changed: list[str], expected: dict[str, str]
) -> None:
    selected = pre_push.select_tests([Path(p) for p in changed], TESTS)

    assert {test.as_posix(): reason for test, reason in selected.items()} == expected


def test_a_dotted_prefix_does_not_select_a_longer_module() -> None:
    tests = {Path("tests/test_x.py"): "from terminal_setup.configs_extra import thing\n"}

    assert pre_push.select_tests([Path("terminal_setup/configs.py")], tests) == {}


@pytest.mark.parametrize(
    ("value", "ci"), [("true", True), ("1", True), ("", False), ("false", False), ("0", False)]
)
def test_ci_runs_the_whole_suite(value: str, ci: bool) -> None:
    assert pre_push.in_ci({"CI": value}) is ci


def test_ci_main_runs_the_whole_tests_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> object:
        calls.append(command)
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(pre_push.subprocess, "run", fake_run)

    assert pre_push.main() == 0
    assert calls == [
        ["uv", "run", "python", ".scripts/bundle_cli_tools_skill.py", "--check"],
        ["uv", "run", "pytest", "tests/"],
    ]


def test_a_failed_bundle_check_stops_the_push_before_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(pre_push, "_bundle_check", lambda: 1)
    monkeypatch.setattr(pre_push, "_pytest", lambda *_t: pytest.fail("pytest ran"))

    assert pre_push.main() == 1


def test_local_main_with_no_mapped_test_runs_no_pytest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(pre_push, "_bundle_check", lambda: 0)
    monkeypatch.setattr(pre_push, "changed_files", lambda: [Path("docs/releases.md")])
    monkeypatch.setattr(pre_push, "_test_texts", lambda: TESTS)
    monkeypatch.setattr(pre_push, "_pytest", lambda *_t: pytest.fail("pytest ran"))

    assert pre_push.main() == 0
    assert "no test file maps to the changed files" in capsys.readouterr().out


def test_local_main_without_the_base_names_the_fetch(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(pre_push, "_bundle_check", lambda: 0)
    monkeypatch.setattr(pre_push, "changed_files", lambda: None)

    assert pre_push.main() == 1
    assert "run git fetch origin" in capsys.readouterr().err
