from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / ".scripts" / "generate_release_changelog.py"
_SPEC = importlib.util.spec_from_file_location("generate_release_changelog", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
generator = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(generator)


def test_a_section_leaves_a_blank_line_between_the_heading_and_the_list() -> None:
    section = generator._build_section("v1.2.0", "2026-09-25", "v1.1.0", ["feat: a (abc1234)"])

    heading = section.index("### Commit delta (auto-generated)")
    assert section[heading + 1] == ""
    assert section[heading + 2] == "- feat: a (abc1234)"


def test_a_section_without_commits_still_leaves_the_blank_line() -> None:
    section = generator._build_section("v1.2.0", "2026-09-25", None, [])

    heading = section.index("### Commit delta (auto-generated)")
    assert section[heading + 1 : heading + 3] == ["", "- No user-visible changes."]
