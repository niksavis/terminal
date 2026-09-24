from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from terminal_setup.configs import _find_git_bash, template_path
from terminal_setup.platform import OperatingSystem, PackageManager, PlatformInfo


def _statusline_bash() -> Path | None:
    if sys.platform == "win32":
        home = Path.home()
        host = PlatformInfo(
            os=OperatingSystem.WINDOWS,
            package_manager=PackageManager.UNKNOWN,
            is_wsl_available=False,
            is_wsl_default_ubuntu=False,
            wsl_distribution=None,
            shell="powershell",
            home=home,
            wezterm_config_dir=None,
            vscode_settings_path=None,
        )
        return _find_git_bash(host)
    found = shutil.which("bash")
    return Path(found) if found else None


_BASH = _statusline_bash()

pytestmark = pytest.mark.skipif(
    _BASH is None or shutil.which("jq") is None,
    reason="statusline.sh needs bash and jq",
)

_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_REQUIRED_TOOLS = ("jq", "awk", "cat", "date", "git", "sed", "tr")


def _minimal_tool_path() -> str:
    directories: list[str] = [str(_BASH.parent)] if _BASH else []
    for tool in _REQUIRED_TOOLS:
        found = shutil.which(tool)
        if found is None:
            continue
        directory = str(Path(found).parent)
        if directory not in directories:
            directories.append(directory)
    return os.pathsep.join(directories)


_EMPTY_CONFIG_DIR = tempfile.mkdtemp(prefix="statusline-no-config-")

_FABLE_WINDOW = {
    "kind": "weekly_scoped",
    "percent": 83,
    "scope": {"model": {"display_name": "Fable"}},
}
_ALL_MODELS_WINDOW = {"kind": "weekly_all", "percent": 60, "scope": None}
_CLOCK = "\uf017"


def write_usage_cache(directory: Path, limits: list[dict], age_seconds: float = 0.0) -> None:
    cache = {
        "cachedUsageUtilization": {
            "fetchedAtMs": (time.time() - age_seconds) * 1000,
            "utilization": {"limits": limits},
        }
    }
    (directory / ".claude.json").write_text(json.dumps(cache), encoding="utf-8")


def render(payload: dict | str, keep_color: bool = False, **env: str) -> str:
    assert _BASH is not None
    result = subprocess.run(
        [str(_BASH), str(template_path("statusline.sh"))],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            "PATH": _minimal_tool_path(),
            "STATUSLINE_WIDTH": "300",
            "STATUSLINE_NERDFONT": "1",
            "CLAUDE_CONFIG_DIR": _EMPTY_CONFIG_DIR,
            **env,
        },
        check=True,
        timeout=30,
    )
    return result.stdout if keep_color else _ANSI.sub("", result.stdout)


def full_payload() -> dict:
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
    output = render(full_payload())
    for expected in ["Opus 4.8", "ctx 42%", "85k/200k", "5h 10%", "wk 20%", "$3.14", "+5 -2"]:
        assert expected in output


def test_statusline_survives_iso_resets_at() -> None:
    payload = full_payload()
    payload["rate_limits"]["seven_day"]["resets_at"] = "2026-07-16T00:00:00Z"
    output = render(payload)
    assert "wk 20%" in output
    assert "$3.14" in output


def test_statusline_cost_is_locale_independent() -> None:
    output = render(full_payload(), LANG="de_DE.UTF-8", LC_ALL="de_DE.UTF-8")
    assert "$3.14" in output


def test_statusline_renders_valid_utf8_in_c_locale() -> None:
    output = render(full_payload())
    assert "ctx 42%" in output


def test_statusline_renders_both_weekly_limits(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW, _FABLE_WINDOW])
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "wk 20%" in output
    assert "fable 83%" in output


def test_statusline_hides_per_model_limit_once_it_folds_in(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW])
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()
    assert "wk 20%" in output


def test_statusline_hides_per_model_limit_past_its_ttl(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_FABLE_WINDOW], age_seconds=3700)
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()


def test_statusline_states_the_weekly_reset_once_after_both(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_ALL_MODELS_WINDOW, _FABLE_WINDOW], age_seconds=17 * 60)
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    weekly = output.split("wk 20%")[1].split("\u2502")[0]
    assert weekly.startswith(" \u00b7 ")
    assert "fable 83%" in weekly
    assert weekly.index("fable") < weekly.index(_CLOCK)
    assert weekly.count(_CLOCK) == 1
    assert "17m" not in output


_TROUGH_FG = "38;2;65;72;104"
_TROUGH_BG = "48;2;65;72;104"


def gauge_shape(raw: str) -> str:
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
            break
        index += 1
    return shape


@pytest.mark.parametrize(
    ("used_percentage", "expected_shape"),
    [
        (0, "....."),
        (5, "....."),
        (14, "H...."),
        (60, "FFF.."),
        (70, "FFFH."),
        (83, "FFFF."),
        (97, "FFFFH"),
        (100, "FFFFF"),
        (137, "FFFFF"),
    ],
)
def test_statusline_gauge_resolves_to_half_a_cell(
    used_percentage: int, expected_shape: str
) -> None:
    payload = full_payload()
    payload["context_window"]["used_percentage"] = used_percentage
    assert gauge_shape(render(payload, keep_color=True)) == expected_shape


def test_statusline_gauge_has_no_texture_to_break_up() -> None:
    raw = render(full_payload(), keep_color=True)
    blocks = {char for char in raw if 0x2580 <= ord(char) <= 0x259F}
    assert blocks <= {"\u2588", "\u258c"}, f"gauge uses a shaded glyph: {blocks}"


_DIM = "38;2;86;95;137"


def colour_before(raw: str, label: str) -> str:
    index = raw.index(label)
    foreground = ""
    for match in _ANSI.finditer(raw[:index]):
        body = match.group(0)[2:-1]
        if body in {"0", ""}:
            foreground = ""
        elif body.startswith("38;"):
            foreground = body
    return foreground


def test_statusline_shows_a_fresh_per_model_sample_in_full_colour(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_FABLE_WINDOW], age_seconds=0)
    raw = render(full_payload(), keep_color=True, CLAUDE_CONFIG_DIR=str(tmp_path))
    assert colour_before(raw, "fable 83%") != _DIM


def test_statusline_dims_a_per_model_sample_as_it_ages(tmp_path: Path) -> None:
    write_usage_cache(tmp_path, [_FABLE_WINDOW], age_seconds=25 * 60)
    raw = render(full_payload(), keep_color=True, CLAUDE_CONFIG_DIR=str(tmp_path))
    assert colour_before(raw, "fable 83%") == _DIM


def test_statusline_survives_unreadable_claude_config(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text('{"cachedUsageUtil', encoding="utf-8")
    output = render(full_payload(), CLAUDE_CONFIG_DIR=str(tmp_path))
    assert "fable" not in output.lower()
    assert "wk 20%" in output
    assert "$3.14" in output


_PORTABLE_CODEPOINTS = frozenset({
    0x00B7,
    0x00BB,
    0x2022,
    0x2026,
    0x2191,
    0x2192,
    0x2193,
    0x2502,
    0x2588,
    0x258C,
})


def git_repo(tmp_path: Path) -> Path:
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
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    git("checkout", "-q", "main")
    git(*author, "commit", "-q", "--allow-empty", "-m", "ours")
    git("config", "branch.main.remote", "origin")
    git("config", "branch.main.merge", "refs/heads/main")
    (repo / "untracked").write_text("dirty", encoding="utf-8")
    return repo


@pytest.mark.parametrize("nerdfont", ["0", "1"])
def test_statusline_glyphs_render_in_every_target_font(tmp_path: Path, nerdfont: str) -> None:
    repo = git_repo(tmp_path)
    write_usage_cache(tmp_path, [_FABLE_WINDOW])
    payload = full_payload()
    payload["cwd"] = str(repo)
    payload["workspace"] = {"project_dir": str(repo), "git_worktree": "a-worktree"}
    output = render(payload, CLAUDE_CONFIG_DIR=str(tmp_path), STATUSLINE_NERDFONT=nerdfont)

    assert "fable 83%" in output and "a-worktree" in output
    for char in output:
        cp = ord(char)
        if cp < 0x80 or cp in _PORTABLE_CODEPOINTS:
            continue
        nerd = nerdfont == "1" and (cp == 0xE0A0 or 0xF000 <= cp <= 0xF2E0)
        assert nerd, f"U+{cp:04X} ({char!r}) is not verified present in the target fonts"


def test_statusline_exits_quietly_on_unparseable_input() -> None:
    output = render("not json at all")
    assert output.strip() == ""
