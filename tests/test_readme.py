from __future__ import annotations

from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"
MAX_README_LINES = 100
MAX_TOOL_TABLE_LINE = 60
TOOL_TABLE_HEADING = "## What you get"


def _lines() -> list[str]:
    return README.read_text(encoding="utf-8").splitlines()


def tool_table_line(lines: list[str]) -> int:
    heading = lines.index(TOOL_TABLE_HEADING)
    return next(
        number
        for number, line in enumerate(lines[heading:], start=heading + 1)
        if line.startswith("|")
    )


def test_readme_stays_within_the_line_limit() -> None:
    count = len(_lines())
    assert count <= MAX_README_LINES, (
        f"README.md has {count} lines; the limit is {MAX_README_LINES}. "
        "Move detail to docs/ and link it."
    )


def test_tool_table_starts_near_the_top_of_the_readme() -> None:
    lines = _lines()
    assert TOOL_TABLE_HEADING in lines, f"README.md has no '{TOOL_TABLE_HEADING}' heading."
    line = tool_table_line(lines)
    assert line <= MAX_TOOL_TABLE_LINE, (
        f"The '{TOOL_TABLE_HEADING}' table starts on line {line}; "
        f"the limit is line {MAX_TOOL_TABLE_LINE}."
    )
