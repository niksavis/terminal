from __future__ import annotations

import importlib.util
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Any

INSTALL_STATE = Path(".basicly/state/install.json")


def _engine_pin() -> Any:
    source = Path(__file__).with_name("engine_pin.py")
    spec = importlib.util.spec_from_file_location("basicly_hook_engine_pin", source)
    if spec is None or spec.loader is None:
        raise ValueError("hook runtime engine_pin.py is missing; rerun the basicly install command")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dist_source(repo_root: Path | None = None) -> str:
    pin = _engine_pin()
    return pin.wheel(pin.installed_version(repo_root))


def _cli_command() -> list[str] | None:
    command = _engine_pin().engine_command(["catalog", "lint"])
    if command is None and shutil.which("uvx"):
        dist_source()
    return command


SKIPPED = (
    "catalog-lint skipped: no basicly to lint with ({reason}); "
    "CI (basicly-gates.yml) runs this check as the deterministic backstop."
)


def main() -> int:
    try:
        command = _cli_command()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if command is None:
        print(
            SKIPPED.format(reason="not installed and uvx is unavailable"),
            file=sys.stderr,
        )
        return 0
    proc = subprocess.run(  # nosec B603
        command, cwd=Path.cwd(), check=False, capture_output=True, text=True, encoding="utf-8"
    )
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
