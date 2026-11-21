from __future__ import annotations

import importlib.util
import os
import subprocess  # nosec B404
import sys
from pathlib import Path

NOTE = Path(__file__).resolve().parents[1] / "kit" / "orch" / "orch_state" / "note.py"


def subject(root: Path) -> str:
    shown = subprocess.run(  # nosec B603 B607
        ["git", "log", "-1", "--format=%s"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return shown.stdout.strip() if shown.returncode == 0 else ""


def item(text: str) -> str | None:
    if not text.endswith(")") or "(" not in text:
        return None
    return text.rsplit("(", 1)[-1][:-1] or None


def main() -> int:
    root = Path.cwd()
    text = subject(root)
    spec = importlib.util.spec_from_file_location("basicly_orch_note", NOTE)
    if not text or spec is None or spec.loader is None or not NOTE.is_file():
        return 0
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        module.note(root, os.environ, item=item(text), last=f"committed: {text}")
    except OSError, ValueError, ImportError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
