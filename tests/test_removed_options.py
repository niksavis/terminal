from __future__ import annotations

import re
from pathlib import Path

import pytest

from terminal_setup import cli

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = [
    ROOT / "README.md",
    ROOT / "terminal-cheat-sheet.md",
    *sorted((ROOT / "docs").glob("**/*.md")),
]


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


@pytest.mark.parametrize("name", sorted(cli.REMOVED_OPTIONS))
def test_a_removed_option_is_not_documented(name: str) -> None:
    found = [
        str(path.relative_to(ROOT))
        for path in DOCUMENTS
        if _mentions(path.read_text(encoding="utf-8"), name)
    ]

    assert found == [], f"{name} was removed; replace it with: {cli.REMOVED_OPTIONS[name]}"


@pytest.mark.parametrize("name", sorted(cli.REMOVED_OPTIONS))
def test_a_removed_option_is_not_in_the_help(name: str) -> None:
    assert not _mentions(cli.build_parser().format_help(), name)


def test_the_guard_finds_a_documented_removed_option() -> None:
    assert _mentions("run terminal-setup --report now", "--report")
    assert not _mentions("run terminal-setup --only report now", "--report")
    assert _mentions("use --only check first", "--only check")
