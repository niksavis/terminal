"""Fixture-driven tests for the Claude Code status line script."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
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


# statusline.sh reads the per-model weekly window out of Claude Code's own config
# file. Point the default render at an empty directory so a test's outcome never
# depends on whether the machine running it happens to have a real one.
_EMPTY_CONFIG_DIR = tempfile.mkdtemp(prefix="statusline-no-config-")

_FABLE_WINDOW = {
    "kind": "weekly_scoped",
    "percent": 83,
    "scope": {"model": {"display_name": "Fable"}},
}
_ALL_MODELS_WINDOW = {"kind": "weekly_all", "percent": 60, "scope": None}
_CLOCK = "\uf017"  # the Nerd Font clock the reset countdown hangs off


def write_usage_cache(directory: Path, limits: list[dict], age_seconds: float = 0.0) -> None:
    """Write the usage snapshot Claude Code caches in its config file."""
    cache = {
        "cachedUsageUtilization": {
            "fetchedAtMs": (time.time() - age_seconds) * 1000,
            "utilization": {"limits": limits},
        }
    }
    (directory / ".claude.json").write_text(json.dumps(cache), encoding="utf-8")


def render(payload: dict | str, keep_color: bool = False, **env: str) -> str:
    """Run statusline.sh with a JSON payload, stripping color unless asked to keep it."""
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
        env={
            "PATH": _minimal_tool_path(),
            "STATUSLINE_WIDTH": "300",
            "CLAUDE_CONFIG_DIR": _EMPTY_CONFIG_DIR,
            **env,
        },
        check=True,
        timeout=30,
    )
    return result.stdout if keep_color else _ANSI.sub("", result.stdout)


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


def test_statusline_renders_both_weekly_limits(tmp_path: Path) -> None:
    """A per-model weekly window must render beside the all-models one, not replace it."""
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW, _FABLE_WINDOW])
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "wk 20%" in output  # all-models, live from the status line payload
    assert "fable 83%" in output  # per-model, sampled from the usage cache


def test_statusline_hides_per_model_limit_once_it_folds_in(tmp_path: Path) -> None:
    """No model-scoped window means no gauge: the model bills against the shared limit."""
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW])
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()
    assert "wk 20%" in output


def test_statusline_hides_per_model_limit_past_its_ttl(tmp_path: Path) -> None:
    """A sample older than Claude Code's own hour-long TTL must go quiet, not go stale."""
    write_usage_cache(tmp_path, [_FABLE_WINDOW], age_seconds=3700)
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()


def test_statusline_states_the_weekly_reset_once_after_both(tmp_path: Path) -> None:
    """One countdown, after both windows: they are the same week and reset together."""
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW, _FABLE_WINDOW], age_seconds=17 * 60)
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    weekly = output.split("wk 20%")[1].split("\u2502")[0]
    assert weekly.startswith(" \u00b7 ")  # grouped, not split off by a full divider
    assert "fable 83%" in weekly
    assert weekly.index("fable") < weekly.index(_CLOCK)  # countdown trails both
    assert weekly.count(_CLOCK) == 1  # and is stated once, not per window
    assert "17m" not in output  # the sample age is never a visible duration


# The gauge draws fill and trough with the same block in two colours, so a
# colour-stripped render cannot tell them apart. Read the colours instead.
_TROUGH_FG = "38;2;65;72;104"
_TROUGH_BG = "48;2;65;72;104"


def gauge_shape(raw: str) -> str:
    """Reduce the first gauge in an uncoloured-stripped render to F / H / . cells."""
    shape, foreground, background, index = "", "", "", 0
    while index < len(raw):
        code = _ANSI.match(raw, index)
        if code:
            body = code.group(0)[2:-1]
            if body in {"0", ""}:
                foreground = background = ""
            elif body.startswith("38;"):
                foreground = body
            elif body.startswith("48;"):
                background = body
            index = code.end()
            continue
        char = raw[index]
        if char == "\u258c":
            shape += "H" if background == _TROUGH_BG else "?"
        elif char == "\u2588":
            shape += "." if foreground == _TROUGH_FG else "F"
        elif shape:
            break  # past the end of the first gauge
        index += 1
    return shape


@pytest.mark.parametrize(
    ("used_percentage", "expected_shape"),
    [
        (0, "....."),
        (5, "....."),
        (14, "H...."),  # a half cell, not an empty bar
        (60, "FFF.."),
        (70, "FFFH."),  # 60 and 70 must not look alike
        (83, "FFFF."),
        (97, "FFFFH"),  # 83 and 97 must not look alike
        (100, "FFFFF"),
        (137, "FFFFF"),  # over limit clamps, never overflows
    ],
)
def test_statusline_gauge_resolves_to_half_a_cell(
    used_percentage: int, expected_shape: str
) -> None:
    """The bar carries ten steps, so neighbouring percentages stay distinguishable."""
    payload = full_payload()
    payload["context_window"]["used_percentage"] = used_percentage
    assert gauge_shape(render(payload, keep_color=True)) == expected_shape


def test_statusline_gauge_has_no_texture_to_break_up() -> None:
    """Fill and trough must be one solid glyph: a dithered trough reads as a gap."""
    raw = render(full_payload(), keep_color=True)
    blocks = {char for char in raw if 0x2580 <= ord(char) <= 0x259F}
    assert blocks <= {"\u2588", "\u258c"}, f"gauge uses a shaded glyph: {blocks}"


def test_statusline_survives_unreadable_claude_config(tmp_path: Path) -> None:
    """Claude Code rewrites that config live: a half-written read costs one segment."""
    (tmp_path / ".claude.json").write_text('{"cachedUsageUtil', encoding="utf-8")
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()
    assert "wk 20%" in output  # the rest of the line is untouched
    assert "$3.14" in output


# Codepoints verified present in the cmap of every console font this status line
# can land in: Consolas, Cascadia Mono, Lucida Console (Windows) and DejaVu Sans
# Mono (WezTerm's Linux default). Widening this set is a font-coverage claim and
# has to be checked against the font files, not assumed from a codepoint looking
# ordinary — ⑂ U+2442, ⎇ U+2387, ⟳ U+27F3 and ✱ U+2731 all looked ordinary and
# are in none of them.
_PORTABLE_CODEPOINTS = frozenset({
    0x00B7,  # · middle dot, sample age
    0x00BB,  # » branch
    0x2022,  # • dirty
    0x2026,  # … truncation
    0x2191,  # ↑ ahead
    0x2192,  # → resets in
    0x2193,  # ↓ behind
    0x2502,  # │ segment separator
    0x2588,  # █ gauge, filled
    0x258C,  # ▌ gauge, half step
})


def git_repo(tmp_path: Path) -> Path:
    """Build a repo that is dirty, ahead and behind, so every git glyph renders."""
    repo = tmp_path / "repo"
    repo.mkdir()
    author = ["-c", "user.email=t@example.com", "-c", "user.name=t"]

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            env={"PATH": os.environ["PATH"]},
        )

    git("init", "-q", "-b", "main")
    git(*author, "commit", "-q", "--allow-empty", "-m", "base")
    git("checkout", "-q", "-b", "upstream")
    git(*author, "commit", "-q", "--allow-empty", "-m", "theirs")
    git("update-ref", "refs/remotes/origin/main", "HEAD")  # a commit main does not have
    git("checkout", "-q", "main")
    git(*author, "commit", "-q", "--allow-empty", "-m", "ours")  # ...and one it does
    git("config", "branch.main.remote", "origin")
    git("config", "branch.main.merge", "refs/heads/main")
    (repo / "untracked").write_text("dirty", encoding="utf-8")
    return repo


@pytest.mark.parametrize("nerdfont", ["0", "1"])
def test_statusline_glyphs_render_in_every_target_font(tmp_path: Path, nerdfont: str) -> None:
    """Every glyph emitted must exist in the fonts it lands in, or it renders as tofu."""
    repo = git_repo(tmp_path)
    write_usage_cache(tmp_path, [_FABLE_WINDOW])
    payload = full_payload()
    payload["cwd"] = str(repo)
    payload["workspace"] = {"project_dir": str(repo), "git_worktree": "a-worktree"}
    output = render(payload, CLAUDE_CONFIG_DIR=str(tmp_path), STATUSLINE_NERDFONT=nerdfont)

    assert "fable 83%" in output and "a-worktree" in output  # the glyphs are in play
    for char in output:
        cp = ord(char)
        if cp < 0x80 or cp in _PORTABLE_CODEPOINTS:
            continue
        # The Nerd Font build may additionally use Powerline U+E0A0 and the FA4
        # range, the span old and current Nerd Fonts both carry.
        nerd = nerdfont == "1" and (cp == 0xE0A0 or 0xF000 <= cp <= 0xF2E0)
        assert nerd, f"U+{cp:04X} ({char!r}) is not verified present in the target fonts"


def test_statusline_exits_quietly_on_unparseable_input() -> None:
    """Input jq cannot parse must produce no output instead of an error render."""
    output = render("not json at all")
    assert output.strip() == ""
