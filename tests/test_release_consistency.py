"""Tests for the release consistency gate.

The gate exists because a nine-step manual checklist let v0.5.0 publish with a
stale version attribute. These assert it refuses each way the checklist can be
missed, rather than only that it accepts a correct release.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".scripts" / "check_release_consistency.py"


def load_script() -> ModuleType:
    """Import the checker by path: .scripts/ is not an importable package."""
    spec = importlib.util.spec_from_file_location("check_release_consistency", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CHECKER = load_script()


def fake_repo(tmp_path: Path, *, pyproject: str, version_attr: str, changelog: str) -> Path:
    """Lay out a synthetic repository the checker can be pointed at."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tmp_path / "terminal_setup").mkdir()
    (tmp_path / "terminal_setup" / "__init__.py").write_text(version_attr, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def consistent(tmp_path: Path) -> Path:
    """Return a synthetic repo that is a correct v0.6.0 release."""
    return fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.6.0"\n',
        version_attr='__version__ = "0.6.0"\n',
        changelog="# Changelog\n\n## v0.6.0 - 2026-09-14\n\n### Highlights\n\n- something\n",
    )


def test_accepts_a_release_where_everything_agrees(tmp_path: Path) -> None:
    """The gate must not cry wolf on a correctly prepared release."""
    assert CHECKER.check("v0.6.0", consistent(tmp_path)) == []


def test_refuses_a_tag_ahead_of_pyproject(tmp_path: Path) -> None:
    """Tagging without bumping is the failure the gate exists for."""
    repo = fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.5.0"\n',
        version_attr='__version__ = "0.5.0"\n',
        changelog="# Changelog\n\n## v0.6.0 - 2026-09-14\n",
    )
    problems = CHECKER.check("v0.6.0", repo)
    assert any("pyproject" in problem and "0.5.0" in problem for problem in problems)


def test_refuses_a_stale_version_attribute(tmp_path: Path) -> None:
    """The exact defect that shipped in v0.5.0: pyproject moved, the attribute did not."""
    repo = fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.6.0"\n',
        version_attr='__version__ = "0.1.0"\n',
        changelog="# Changelog\n\n## v0.6.0 - 2026-09-14\n",
    )
    problems = CHECKER.check("v0.6.0", repo)
    assert any("__version__" in problem and "0.1.0" in problem for problem in problems)


def test_refuses_a_missing_changelog_section(tmp_path: Path) -> None:
    """A release with no notes must fail before the tag, not publish empty notes."""
    repo = fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.6.0"\n',
        version_attr='__version__ = "0.6.0"\n',
        changelog="# Changelog\n\n## v0.5.0 - 2026-09-12\n",
    )
    assert any("CHANGELOG" in problem for problem in CHECKER.check("v0.6.0", repo))


def test_refuses_an_undated_changelog_heading(tmp_path: Path) -> None:
    """The release workflow parses the date, so an undated heading is not a section."""
    repo = fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.6.0"\n',
        version_attr='__version__ = "0.6.0"\n',
        changelog="# Changelog\n\n## v0.6.0\n",
    )
    assert any("CHANGELOG" in problem for problem in CHECKER.check("v0.6.0", repo))


@pytest.mark.parametrize("tag", ["0.6.0", "v0.6", "v0.6.0-rc1", "release-0.6.0", ""])
def test_refuses_a_malformed_tag(tmp_path: Path, tag: str) -> None:
    """A tag that is not vX.Y.Z cannot be compared, so it is refused rather than skipped."""
    assert CHECKER.check(tag, consistent(tmp_path)) != []


def test_reports_every_disagreement_at_once(tmp_path: Path) -> None:
    """One run must name all three, so a release is not fixed one failed run at a time."""
    repo = fake_repo(
        tmp_path,
        pyproject='[project]\nname = "terminal"\nversion = "0.5.0"\n',
        version_attr='__version__ = "0.1.0"\n',
        changelog="# Changelog\n\n## v0.5.0 - 2026-09-12\n",
    )
    assert len(CHECKER.check("v0.6.0", repo)) == 3


def test_reads_the_version_attribute_from_source_not_import(tmp_path: Path) -> None:
    """Importing would resolve through stale bytecode or a shadowing egg-info."""
    repo = consistent(tmp_path)
    (repo / "terminal_setup" / "__init__.py").write_text(
        '__version__ = "9.9.9"\n', encoding="utf-8"
    )
    assert CHECKER.module_version(repo) == "9.9.9"  # no reimport, no cache to go stale
