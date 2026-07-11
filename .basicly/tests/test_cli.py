"""Integration tests for the CLI."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def run_basicly(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the basicly CLI with the given arguments."""
    env = {"PYTHONPATH": str(REPO_ROOT / ".basicly")}
    return subprocess.run(
        [sys.executable, "-m", "basicly.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_build_idempotent() -> None:
    """Two build runs with no source changes should produce no diff."""
    result1 = run_basicly("build")
    assert result1.returncode == 0
    result2 = run_basicly("build")
    assert result2.returncode == 0
    assert "No files changed" in result2.stdout


def test_cli_check_passes_after_build() -> None:
    """Check should pass immediately after a build."""
    run_basicly("build")
    result = run_basicly("check")
    assert result.returncode == 0
    assert "up to date" in result.stdout


def test_cli_check_fails_after_manual_edit(tmp_path: Path) -> None:
    """Check should fail after a generated file is edited manually."""
    work = tmp_path / "repo"
    shutil.copytree(REPO_ROOT, work, ignore=shutil.ignore_patterns(".git", ".venv"))
    env = {"PYTHONPATH": str(work / ".basicly")}
    subprocess.run(
        [sys.executable, "-m", "basicly.cli", "build"],
        cwd=work,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    agents = work / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "basicly.cli", "check"],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Stale generated files detected" in result.stderr


def test_cli_build_target_only() -> None:
    """Build --target should only touch that target's outputs but preserve the manifest."""
    run_basicly("build")
    result = run_basicly("build", "--target", "claude")
    assert result.returncode == 0
    assert "copilot-instructions.md" not in result.stdout
    # Manifest must still list outputs from other targets so check passes.
    result_check = run_basicly("check")
    assert result_check.returncode == 0


def test_cli_unknown_target() -> None:
    """Build --target with an unknown target should fail cleanly."""
    result = run_basicly("build", "--target", "unknown")
    assert result.returncode == 1
    assert "Unknown target" in result.stderr
