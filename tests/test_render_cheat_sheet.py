from __future__ import annotations

import importlib.util
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

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
    assert MD_PATH.exists(), "terminal-cheat-sheet.md should exist"


def test_html_output_exists() -> None:
    assert HTML_PATH.exists(), "terminal-cheat-sheet.html should exist"


def test_html_is_in_sync() -> None:
    result = _run_renderer("--check")
    assert result.returncode == 0, result.stderr


def test_renderer_renders_valid_html() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "<html" in html
    assert "</html>" in html
    assert "<style>" in html
    assert "<script>" in html
    assert 'id="search"' in html


def test_renderer_escapes_html_in_table_cells() -> None:
    html = HTML_PATH.read_text(encoding="utf-8")
    assert "<script>" in html
    assert "&lt;" in html or "<code>" in html


def _renderer_module() -> object:
    spec = importlib.util.spec_from_file_location("render_cheat_sheet", RENDERER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_fenced_block_renders_as_one_copyable_block() -> None:
    renderer = _renderer_module()
    md = "## Install\n\n```powershell\n$env:X = 'a'\nirm https://example.test/i.ps1 | iex\n```\n"

    page = renderer.render_sections(renderer.parse_markdown(md))  # type: ignore[attr-defined]

    assert '<pre class="code-block" data-language="powershell"><code>' in page
    assert "$env:X = &#x27;a&#x27;\nirm https://example.test/i.ps1 | iex</code></pre>" in page
    assert "```" not in page
    assert "<code> </code>" not in page


def test_an_unclosed_fence_is_refused_by_line() -> None:
    renderer = _renderer_module()

    with pytest.raises(ValueError, match="line 2: the code block opened with ```bash"):
        renderer.parse_markdown("## Install\n```bash\ncurl x | sh\n")  # type: ignore[attr-defined]


def test_the_cheat_sheet_leaves_no_fence_as_text() -> None:
    renderer = _renderer_module()

    sections = renderer.parse_markdown(MD_PATH.read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    texts = [block["text"] for section in sections for block in section["body"] if "text" in block]
    assert not [text for text in texts if "```" in text]
