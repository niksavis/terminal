"""Tests for the projection planner."""

from __future__ import annotations

from pathlib import Path

from basicly.loader import load_fragments, load_targets
from basicly.planner import plan_outputs

FIXTURES = Path(__file__).parent / "fixtures"


def test_plan_outputs() -> None:
    """The planner produces the expected output files for fixture targets."""
    targets = load_targets(FIXTURES / "targets")
    target_names = {t.name for t in targets}
    fragments = load_fragments(FIXTURES, target_names)
    planned = plan_outputs(fragments, targets, Path("/repo"))

    paths = {p.output_path for p in planned}
    assert Path("/repo/AGENTS.md") in paths
    assert Path("/repo/.claude/CLAUDE.md") in paths
    assert Path("/repo/.github/copilot-instructions.md") in paths
    assert Path("/repo/.github/instructions/python-style.instructions.md") in paths
    assert Path("/repo/.claude/rules/python-style.md") not in paths


def test_agents_baseline_only_all_fragments() -> None:
    """The cross-tool baseline only includes applies_to: [all] fragments."""
    targets = load_targets(FIXTURES / "targets")
    target_names = {t.name for t in targets}
    fragments = load_fragments(FIXTURES, target_names)
    planned = plan_outputs(fragments, targets, Path("/repo"))

    agents = next(p for p in planned if p.output_path == Path("/repo/AGENTS.md"))
    ids = [f.id for f in agents.fragments]
    assert "claude-defaults" not in ids
    assert "copilot-defaults" not in ids
    assert ids == ["project-defaults", "core-rules", "python-style"]


def test_sort_order() -> None:
    """Fragments are sorted by priority descending, then category, then id."""
    targets = load_targets(FIXTURES / "targets")
    target_names = {t.name for t in targets}
    fragments = load_fragments(FIXTURES, target_names)
    planned = plan_outputs(fragments, targets, Path("/repo"))

    agents = next(p for p in planned if p.output_path == Path("/repo/AGENTS.md"))
    ids = [f.id for f in agents.fragments]
    assert ids == ["project-defaults", "core-rules", "python-style"]
