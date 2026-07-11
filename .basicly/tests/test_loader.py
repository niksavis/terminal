"""Tests for the fragment and target loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from basicly.loader import load_fragments, load_targets
from basicly.schema import ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_fragments() -> None:
    """All fixture fragments are loaded with correct ids."""
    fragments = load_fragments(FIXTURES, {"claude", "copilot"})
    ids = {f.id for f in fragments}
    assert ids == {
        "project-defaults",
        "core-rules",
        "python-style",
        "claude-defaults",
        "copilot-defaults",
    }


def test_fragment_fields() -> None:
    """Scoped and unscoped fragments are parsed correctly."""
    fragments = load_fragments(FIXTURES, {"claude", "copilot"})
    by_id = {f.id: f for f in fragments}
    assert by_id["python-style"].is_scoped is True
    assert by_id["python-style"].scope_paths == ["**/*.py"]
    assert by_id["project-defaults"].is_scoped is False


def test_missing_required_field(tmp_path: Path) -> None:
    """A fragment missing required front matter fields raises ValidationError."""
    fragment = tmp_path / "bad.fragment.md"
    fragment.write_text("---\nid: bad\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_fragments(tmp_path, {"claude"})


def test_unknown_category(tmp_path: Path) -> None:
    """An unknown category value raises ValidationError."""
    fragment = tmp_path / "bad.fragment.md"
    fragment.write_text(
        "---\nid: bad\ndescription: x\ncategory: not-a-category\napplies_to: [all]\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_fragments(tmp_path, {"claude"})


def test_unknown_target_in_applies_to(tmp_path: Path) -> None:
    """An applies_to value that is not a registered target raises ValidationError."""
    fragment = tmp_path / "bad.fragment.md"
    fragment.write_text(
        "---\nid: bad\ndescription: x\ncategory: project\napplies_to: [unknown]\n---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_fragments(tmp_path, {"claude"})


def test_load_targets() -> None:
    """All fixture target registries are loaded."""
    targets = load_targets(FIXTURES / "targets")
    names = {t.name for t in targets}
    assert names == {"claude", "copilot"}


def test_extension_fields_default_to_safe_values() -> None:
    """Fragments without extension fields get phase-1-safe defaults."""
    fragments = load_fragments(FIXTURES, {"claude", "copilot"})
    by_id = {f.id: f for f in fragments}
    fragment = by_id["python-style"]
    assert fragment.source == "core"
    assert fragment.override is False
    assert fragment.replaces == []
    assert fragment.extends == []


def test_extension_fields_are_parsed(tmp_path: Path) -> None:
    """Extension fields are loaded when present."""
    fragment = tmp_path / "user.fragment.md"
    fragment.write_text(
        "---\n"
        "id: user-style\n"
        "description: User style\n"
        "category: code-style\n"
        "applies_to: [all]\n"
        "source: user\n"
        "override: true\n"
        "replaces: [python-style]\n"
        "extends: [project-defaults]\n"
        "---\n\n"
        "body\n",
        encoding="utf-8",
    )
    fragments = load_fragments(tmp_path, {"claude"})
    assert len(fragments) == 1
    f = fragments[0]
    assert f.source == "user"
    assert f.override is True
    assert f.replaces == ["python-style"]
    assert f.extends == ["project-defaults"]


def test_invalid_source_value(tmp_path: Path) -> None:
    """An invalid source value raises ValidationError."""
    fragment = tmp_path / "bad.fragment.md"
    fragment.write_text(
        "---\n"
        "id: bad\n"
        "description: x\n"
        "category: project\n"
        "applies_to: [all]\n"
        "source: invalid\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_fragments(tmp_path, {"claude"})


def test_replaces_must_be_string_list(tmp_path: Path) -> None:
    """A non-list replaces value raises ValidationError."""
    fragment = tmp_path / "bad.fragment.md"
    fragment.write_text(
        "---\n"
        "id: bad\n"
        "description: x\n"
        "category: project\n"
        "applies_to: [all]\n"
        "replaces: not-a-list\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_fragments(tmp_path, {"claude"})
