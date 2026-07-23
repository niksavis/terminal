"""Fixture-driven tests for the Claude Code status line script."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from terminal_setup.configs import template_path

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="statusline.sh needs bash and jq",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

# statusline.sh shells out to these. A hardcoded "/usr/bin:/bin" is Linux-only:
# on Windows these ship via winget / Git Bash and live outside /usr/bin, so
# pinning that PATH hides them and the script fails. Derive each tool's real
# directory instead, keeping the PATH minimal but portable.
_REQUIRED_TOOLS = ("bash", "jq", "awk", "cat", "date", "git", "sed", "tr")


def _minimal_tool_path() -> str:
    """Build a minimal PATH from the real locations of the tools statusline.sh needs."""
    directories: list[str] = []
    for tool in _REQUIRED_TOOLS:
        found = shutil.which(tool)
        if found is None:
            continue
        directory = str(Path(found).parent)
        if directory not in directories:
            directories.append(directory)
    return os.pathsep.join(directories)


def render(payload: dict | str, **env: str) -> str:
    """Run statusline.sh with a JSON payload and return the color-stripped output."""
    # Invoke bash by absolute path: the bare name "bash" resolves to the
    # Windows WSL launcher stub, not Git Bash. Decode as UTF-8 explicitly since
    # the status line emits Nerd Font glyphs the Windows default (cp1252) rejects.
    bash = shutil.which("bash")
    assert bash is not None  # guaranteed by the module-level skipif
    result = subprocess.run(
        [bash, str(template_path("statusline.sh"))],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={"PATH": _minimal_tool_path(), "STATUSLINE_WIDTH": "300", **env},
        check=True,
        timeout=30,
    )
    return _ANSI.sub("", result.stdout)


def full_payload() -> dict:
    """Return a payload exercising every segment of the status line."""
    return {
        "model": {"display_name": "Opus 4.8"},
        "workspace": {"project_dir": "/tmp/repo"},
        "cwd": "/tmp/repo",
        "cost": {
            "total_cost_usd": 3.14159,
            "total_duration_ms": 3600000,
            "total_lines_added": 5,
            "total_lines_removed": 2,
        },
        "context_window": {
            "used_percentage": 42.5,
            "total_input_tokens": 85000,
            "context_window_size": 200000,
        },
        "rate_limits": {
            "five_hour": {"used_percentage": 10, "resets_at": 9999999999},
            "seven_day": {"used_percentage": 20, "resets_at": 9999999999},
        },
    }


def test_statusline_renders_all_segments() -> None:
    """The full payload must render model, gauges, cost, and churn."""
    output = render(full_payload())
    for expected in ["Opus 4.8", "ctx 42%", "85k/200k", "5h 10%", "wk 20%", "$3.14", "+5 -2"]:
        assert expected in output


def test_statusline_survives_iso_resets_at() -> None:
    """A non-epoch resets_at must not abort the render (regression: arithmetic on ISO)."""
    payload = full_payload()
    payload["rate_limits"]["seven_day"]["resets_at"] = "2026-07-16T00:00:00Z"
    output = render(payload)
    assert "wk 20%" in output
    assert "$3.14" in output


def test_statusline_cost_is_locale_independent() -> None:
    """Cost math must use C-locale decimals even under a comma-decimal locale."""
    output = render(full_payload(), LANG="de_DE.UTF-8", LC_ALL="de_DE.UTF-8")
    assert "$3.14" in output


def test_statusline_renders_valid_utf8_in_c_locale() -> None:
    """Glyph slicing must stay character-aware even in a stripped non-UTF-8 env."""
    output = render(full_payload())  # env carries no LANG/LC_*: bash starts in C
    assert "ctx 42%" in output  # decoding above already proves valid UTF-8


def test_statusline_exits_quietly_on_unparseable_input() -> None:
    """Input jq cannot parse must produce no output instead of an error render."""
    output = render("not json at all")
    assert output.strip() == ""
