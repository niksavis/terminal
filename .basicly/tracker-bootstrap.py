from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BOOTSTRAP_OWNER = "basicly-tracker"
SOURCE = (
    "https://github.com/niksavis/basicly/releases/download/v0.49.3/basicly-0.49.3-py3-none-any.whl"
)
TOOL = "basicly"
MINIMUM_PYTHON = (3, 14)


def _run(
    command: list[str], *, cwd: Path | None = None, capture_output: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, capture_output=capture_output, text=True, encoding="utf-8", check=False
    )


def _provision() -> list[str]:
    uv = shutil.which("uv")
    uvx = shutil.which("uvx") if uv is None else None
    if (uv is None and uvx is None) or not SOURCE:
        raise ValueError(
            "Install uv, then rerun this repository's .basicly/tracker-bootstrap.py; "
            "implementation is blocked until persistent tracker memory is available."
        )
    if uv is None:
        return [str(uvx), "--python", ">=3.14", "--from", SOURCE, TOOL]
    installed = _run(
        [uv, "tool", "install", "--upgrade", "--python", ">=3.14", SOURCE], capture_output=False
    )
    if installed.returncode != 0:
        raise ValueError(
            "uv could not install the repository's tracker runtime. Restore package access "
            "before starting implementation; unrelated tools were not overwritten."
        )
    return [uv, "tool", "run", "--python", ">=3.14", "--from", SOURCE, TOOL]


def _bundle_command(bundle: Path) -> list[str]:
    if sys.version_info >= MINIMUM_PYTHON:
        return [sys.executable, str(bundle)]
    uv = shutil.which("uv")
    if uv is None:
        raise ValueError("Install uv to provision Python 3.14 before implementation.")
    return [uv, "run", "--no-project", "--python", ">=3.14", "python", str(bundle)]


def _bootstrap() -> int:
    root = Path(__file__).resolve().parent.parent
    bundle = root / ".basicly/tracker.pyz"
    executable = None if TOOL == "basicly-tracker" and bundle.is_file() else shutil.which(TOOL)
    tail = ["tracker", "bootstrap"] if TOOL == "basicly" else ["bootstrap"]
    if executable is not None:
        capable = _run([executable, *tail, "--help"])
        if capable.returncode != 0:
            executable = None
    if executable is not None:
        command = [executable]
    elif TOOL == "basicly-tracker" and bundle.is_file():
        command = _bundle_command(bundle)
    else:
        command = _provision()
    done = _run(
        [*command, *tail, "--repository", str(root)],
        cwd=root,
    )
    if done.returncode != 0:
        sys.stderr.write(done.stderr)
        return done.returncode
    report = json.loads(done.stdout)
    if report.get("ready") is not True:
        raise ValueError(
            "Tracker startup established no persistent memory; implementation is blocked."
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    try:
        return _bootstrap()
    except (OSError, ValueError) as exc:
        print(f"{BOOTSTRAP_OWNER} bootstrap: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
