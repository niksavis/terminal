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
