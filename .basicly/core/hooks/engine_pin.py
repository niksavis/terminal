from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

RELEASES = "https://github.com/niksavis/basicly/releases/download"
INSTALL_STATE = Path(".basicly/state/install.json")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PROBE_TIMEOUT_S = 10.0


class EngineSkewError(ValueError):
    pass


def installed_version(repo_root: Path | None = None) -> str:
    state = (repo_root or Path.cwd()) / INSTALL_STATE
    try:
        version = json.loads(state.read_text(encoding="utf-8"))["basicly_version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(
            "cannot read the installed basicly version; rerun the basicly install command"
        ) from exc
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise ValueError(
            "the installed basicly version is invalid; rerun the basicly install command"
        )
    return version


def pinned_version(repo_root: Path | None = None) -> str | None:
    if not ((repo_root or Path.cwd()) / INSTALL_STATE).is_file():
        return None
    return installed_version(repo_root)


def wheel(version: str) -> str:
    return f"{RELEASES}/v{version}/basicly-{version}-py3-none-any.whl"


def path_version(executable: str) -> str | None:
    try:
        shown = subprocess.run(  # nosec B603
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT_S,
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    found = re.search(r"basicly\s+(" + VERSION.pattern + r")\b", shown.stdout)
    return found.group(1) if found else None


def module_version() -> str | None:
    if importlib.util.find_spec("basicly") is None:
        return None
    try:
        return importlib.metadata.version("basicly")
    except importlib.metadata.PackageNotFoundError:
        return None


def skew_message(found: str, have: str | None, want: str) -> str:
    shown = have or "an unknown version"
    return (
        f"basicly on PATH ({found}) is {shown}, but this repository is installed at {want}. "
        f"Upgrade it: uv tool install --force --python '>=3.14' {wheel(want)}"
    )


def engine_command(
    args: list[str], repo_root: Path | None = None, *, uvx_fallback: bool = True
) -> list[str] | None:
    want = pinned_version(repo_root)
    found = shutil.which("basicly")
    have = path_version(found) if found and want else None
    if found and (want is None or have == want):
        return [found, *args]
    module = module_version()
    if module is not None and (want is None or module == want):
        return [sys.executable, "-m", "basicly.cli", *args]
    uvx = shutil.which("uvx") if uvx_fallback else None
    if want and uvx:
        if found:
            print(
                f"{skew_message(found, have, want)}. Running {want} through uvx instead.",
                file=sys.stderr,
            )
        return [uvx, "--from", wheel(want), "basicly", *args]
    if found and want:
        raise EngineSkewError(skew_message(found, have, want))
    return None
