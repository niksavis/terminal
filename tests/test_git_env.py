from __future__ import annotations

import ast
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_SPAWNS = {"run", "call", "check_call", "check_output", "Popen"}
_CLEAN = "environment_without_git"


def _is_clean_call(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == _CLEAN


def _clean_environment(node: ast.expr | None) -> bool:
    if _is_clean_call(node):
        return True
    if not isinstance(node, ast.Dict):
        return False
    pairs = zip(node.keys, node.values, strict=True)
    return all(key is not None or _is_clean_call(value) for key, value in pairs)


def _starts_git(call: ast.Call) -> bool:
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in _SPAWNS):
        return False
    if not call.args or not isinstance(call.args[0], ast.List | ast.Tuple):
        return False
    first = call.args[0].elts[0] if call.args[0].elts else None
    return isinstance(first, ast.Constant) and first.value == "git"


def leaking_git_spawns(source: str, name: str) -> list[str]:
    leaks = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and _starts_git(node)):
            continue
        env = next((keyword.value for keyword in node.keywords if keyword.arg == "env"), None)
        if not _clean_environment(env):
            leaks.append(
                f"{name}:{node.lineno}: git runs with the inherited GIT_ variables; "
                "pass env=environment_without_git() from tests/git_env.py"
            )
    return leaks


def test_no_test_starts_git_with_the_inherited_git_variables() -> None:
    files = sorted(_TESTS.rglob("*.py"))
    assert _TESTS / "test_generate_release_changelog.py" in files
    leaks = [
        leak
        for path in files
        for leak in leaking_git_spawns(
            path.read_text(encoding="utf-8"), path.relative_to(_TESTS).as_posix()
        )
    ]
    assert leaks == []


def test_a_git_run_without_env_is_refused_with_its_file_and_line() -> None:
    source = 'import subprocess\nsubprocess.run(["git", "init"], check=True)\n'

    assert leaking_git_spawns(source, "leaking.py") == [
        "leaking.py:2: git runs with the inherited GIT_ variables; "
        "pass env=environment_without_git() from tests/git_env.py"
    ]


def test_a_git_run_that_spreads_os_environ_is_refused() -> None:
    source = (
        'import os, subprocess\nsubprocess.run(["git", "init"], env={**os.environ, "A": "1"})\n'
    )

    assert len(leaking_git_spawns(source, "spread.py")) == 1


def test_a_git_run_with_the_clean_environment_passes() -> None:
    source = (
        "import subprocess\n"
        'subprocess.run(["git", "init"], env=environment_without_git())\n'
        'subprocess.run(["git", "init"], env={**environment_without_git(), "A": "1"})\n'
        'subprocess.run(["git", "init"], env={"PATH": "/usr/bin"})\n'
    )

    assert leaking_git_spawns(source, "clean.py") == []
