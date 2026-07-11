"""Tests for skill collection projection helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from basicly.schema import ValidationError
from basicly.skills import (
    SKILLS_SOURCE_DIR,
    check_synced_skills,
    discover_skills,
    resolve_skill_roots,
    sync_skills,
)


def _write_skill(repo_root: Path, slug: str, name: str, description: str) -> None:
    path = repo_root / SKILLS_SOURCE_DIR / slug / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "---",
            f"name: {name}",
            f"description: {description}",
            "---",
            "",
            f"# {name}",
            "",
            "## When To Use",
            "- Example.",
        ])
        + "\n",
        encoding="utf-8",
    )


def test_discover_skills_loads_frontmatter(tmp_path: Path) -> None:
    """discover_skills should read source skills and parse frontmatter."""
    _write_skill(tmp_path, "tool-ripgrep", "tool-ripgrep", "Use ripgrep for fast code search.")

    skills = discover_skills(tmp_path)

    assert [skill.slug for skill in skills] == ["tool-ripgrep"]
    assert skills[0].name == "tool-ripgrep"
    assert skills[0].description == "Use ripgrep for fast code search."


def test_discover_skills_requires_frontmatter_fields(tmp_path: Path) -> None:
    """discover_skills should fail when required frontmatter fields are missing."""
    path = tmp_path / SKILLS_SOURCE_DIR / "tool-ripgrep" / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# missing frontmatter\n", encoding="utf-8")

    with pytest.raises(ValidationError):
        discover_skills(tmp_path)


def test_sync_and_check_skills(tmp_path: Path) -> None:
    """sync_skills writes skills to roots and check_synced_skills validates parity."""
    _write_skill(tmp_path, "tool-ripgrep", "tool-ripgrep", "Use ripgrep for fast code search.")
    roots = resolve_skill_roots(tmp_path, roots=[".claude/skills"], use_default_roots=False)

    result = sync_skills(tmp_path, roots)

    assert len(result.written) == 1
    assert len(check_synced_skills(tmp_path, roots)) == 0

    target = roots[0] / "tool-ripgrep" / "SKILL.md"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    mismatches = check_synced_skills(tmp_path, roots)
    assert mismatches == [(target, "content mismatch")]
