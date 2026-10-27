from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from terminal_setup.configs import template_path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("zsh") is None, reason="requires zsh")
@pytest.mark.parametrize("supported", [True, False])
def test_zsh_generates_fzf_integration_only_once(tmp_path: Path, supported: bool) -> None:
    calls = tmp_path / "calls.txt"
    template = template_path("zshrc").read_text(encoding="utf-8")
    for filename, marker in (
        ("key-bindings.zsh", "FZF_PROBE_BINDINGS"),
        ("completion.zsh", "FZF_PROBE_COMPLETION"),
    ):
        fallback = tmp_path / filename
        fallback.write_text(f"typeset -g {marker}=yes\n", encoding="utf-8")
        original = f"/usr/share/doc/fzf/examples/{filename}"
        assert template.count(original) == 2
        template = template.replace(original, shlex.quote(fallback.as_posix()))
    local_template = tmp_path / "zshrc"
    local_template.write_text(template, encoding="utf-8")
    script = """
fzf() {
  print -r -- "$*" >> "$FZF_PROBE_CALLS"
  if [[ "$FZF_PROBE_SUPPORTED" == yes ]]; then
    print -r -- 'typeset -g FZF_PROBE_INITIALIZED=yes'
  else
    return 1
  fi
}
source "$ZSH_TEMPLATE"
print -r -- "initialized=${FZF_PROBE_INITIALIZED:-no}"
print -r -- "temporary_variable=${_terminal_fzf_init-unset}"
print -r -- "bindings=${FZF_PROBE_BINDINGS:-no}"
print -r -- "completion=${FZF_PROBE_COMPLETION:-no}"
"""
    result = subprocess.run(
        ["zsh", "-f", "-c", script],
        env={
            **os.environ,
            "HOME": str(tmp_path),
            "ZDOTDIR": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "FZF_PROBE_CALLS": str(calls),
            "FZF_PROBE_SUPPORTED": "yes" if supported else "no",
            "ZSH_TEMPLATE": str(local_template),
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert calls.read_text().splitlines() == ["--zsh"]
    assert f"initialized={'yes' if supported else 'no'}" in result.stdout
    assert "temporary_variable=unset" in result.stdout
    assert f"bindings={'no' if supported else 'yes'}" in result.stdout
    assert f"completion={'no' if supported else 'yes'}" in result.stdout


HERDR_PROBE = """
source "$ZSH_TEMPLATE"
print -r -- "completion=${_comps[herdr]:-none}"
print -r -- "first_fpath=${fpath[1]}"
print -r -- "temporary_variable=${_terminal_completions-unset}"
"""
FAKE_HERDR = """#!/bin/sh
echo "$*" >> "$HERDR_PROBE_CALLS"
printf '#compdef herdr\\n_herdr() { compadd probe }\\n'
"""


def _start_zsh(home: Path) -> str:
    result = subprocess.run(
        ["zsh", "-f", "-c", HERDR_PROBE],
        env={
            **os.environ,
            "HOME": str(home),
            "ZDOTDIR": str(home),
            "PATH": "/usr/bin:/bin",
            "HERDR_PROBE_CALLS": str(home / "calls.txt"),
            "ZSH_TEMPLATE": str(template_path("zshrc")),
        },
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return result.stdout


def _herdr_calls(home: Path) -> list[str]:
    calls = home / "calls.txt"
    return calls.read_text().splitlines() if calls.exists() else []


@pytest.mark.skipif(shutil.which("zsh") is None, reason="requires zsh")
def test_zsh_caches_herdr_completion_until_herdr_changes(tmp_path: Path) -> None:
    herdr = tmp_path / ".local" / "bin" / "herdr"
    herdr.parent.mkdir(parents=True)
    herdr.write_text(FAKE_HERDR, encoding="utf-8")
    herdr.chmod(0o755)
    cache = tmp_path / ".cache" / "zsh" / "completions"

    first = _start_zsh(tmp_path)
    second = _start_zsh(tmp_path)
    assert _herdr_calls(tmp_path) == ["completion zsh"]
    later = (cache / "_herdr").stat().st_mtime + 60
    os.utime(herdr, (later, later))
    _start_zsh(tmp_path)

    assert _herdr_calls(tmp_path) == ["completion zsh", "completion zsh"]
    for output in (first, second):
        assert "completion=_herdr" in output
        assert f"first_fpath={cache}" in output
        assert "temporary_variable=unset" in output


@pytest.mark.skipif(shutil.which("zsh") is None, reason="requires zsh")
def test_zsh_adds_no_completion_folder_without_herdr(tmp_path: Path) -> None:
    output = _start_zsh(tmp_path)

    assert "completion=none" in output
    assert ".cache/zsh/completions" not in output
    assert not (tmp_path / ".cache" / "zsh" / "completions").exists()


@pytest.mark.skipif(shutil.which("wezterm") is None, reason="requires the WezTerm CLI")
def test_wezterm_platform_and_callback_consumer_check() -> None:
    result = subprocess.run(
        [
            "wezterm",
            "--config-file",
            str(REPO_ROOT / ".scripts/check_wezterm_callbacks.lua"),
            "show-keys",
            "--lua",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "TERMINAL_CALLBACK_CHECK_PASS" in result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("wezterm") is None, reason="requires the WezTerm CLI")
@pytest.mark.parametrize(
    ("injected", "expected"),
    [
        ("config.enable_kitty_graphics = true", "Kitty graphics must be disabled"),
        (
            'if not is_windows and not is_wsl then config.front_end = "WebGpu" end',
            "native builds must inherit",
        ),
        (
            'wezterm.on("format-tab-title", function() return "title" end)',
            "custom format-tab-title",
        ),
        (
            'wezterm.on("update-right-status", function() '
            'wezterm.run_child_process({"git", "status"}) end)',
            "blocking callback operation",
        ),
        (
            'wezterm.on("format-window-title", function() return "title" end)',
            "custom format-window-title",
        ),
        (
            'wezterm.on("update-right-status", function() io.open("fixture-nonexistent") end)',
            "blocking callback operation: open",
        ),
        (
            'wezterm.on("update-right-status", function() io.popen("exit 0") end)',
            "blocking callback operation: popen",
        ),
        (
            'wezterm.on("update-right-status", function() os.execute("exit 0") end)',
            "blocking callback operation: execute",
        ),
        (
            'wezterm.on("update-right-status", function() '
            'wezterm.background_child_process({"git", "status"}) end)',
            "blocking callback operation: background_child_process",
        ),
    ],
)
def test_wezterm_check_rejects_unsafe_template_changes(
    tmp_path: Path, injected: str, expected: str
) -> None:
    scripts = tmp_path / ".scripts"
    scripts.mkdir()
    checker = scripts / "check_wezterm_callbacks.lua"
    shutil.copyfile(REPO_ROOT / ".scripts/check_wezterm_callbacks.lua", checker)
    templates = tmp_path / "terminal_setup/templates"
    templates.mkdir(parents=True)
    source = template_path("wezterm.lua").read_text(encoding="utf-8")
    before, ending = source.rsplit("return config", 1)
    (templates / "wezterm.lua").write_text(
        before + injected + "\nreturn config" + ending, encoding="utf-8"
    )
    result = subprocess.run(
        ["wezterm", "--config-file", str(checker), "show-keys", "--lua"],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    output = result.stdout + result.stderr
    assert "TERMINAL_CALLBACK_CHECK_PASS" not in output
    assert expected in output
