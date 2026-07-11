"""Tests for the cheat sheet HTML renderer."""

from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER = REPO_ROOT / ".scripts" / "render-cheat-sheet.py"
MD_PATH = REPO_ROOT / "terminal-cheat-sheet.md"
HTML_PATH = REPO_ROOT / "terminal-cheat-sheet.html"


def _run_renderer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RENDERER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )  # nosec


def test_markdown_source_exists() -> None:
    """The markdown cheat sheet must exist."""
    assert MD_PATH.exists(), "terminal-cheat-sheet.md should exist"


def test_html_output_exists() -> None:
    """The rendered HTML cheat sheet must exist."""
    assert HTML_PATH.exists(), "terminal-cheat-sheet.html should exist"


def test_html_is_in_sync() -> None:
    """The rendered HTML must be up to date with the markdown source."""
    result = _run_renderer("--check")
    assert result.returncode == 0, result.stderr


def test_renderer_renders_valid_html() -> None:
    """The rendered HTML must contain expected structure."""
    html = HTML_PATH.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<style>" in html
    assert "<script>" in html
    assert 'id="search"' in html


def test_renderer_escapes_html_in_table_cells() -> None:
    """Special characters in markdown table cells must be escaped."""
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "<script>" in html
    assert "&lt;" in html or "<code>" in html
