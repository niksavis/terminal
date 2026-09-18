from __future__ import annotations

import subprocess  # nosec B404
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _kit_cli() -> Path:
    installed = _HERE.parent / "kit" / "comments" / "cli.py"
    if installed.exists():
        return installed
    raise SystemExit("no-comments: the comments kit is missing from beside this hook")


def main(argv: list[str] | None = None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    if not paths:
        return 0
    completed = subprocess.run(  # nosec B603
        [sys.executable, str(_kit_cli()), "check", *paths],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return 0
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    sys.stderr.write(
        "no-comments: the code is the source of truth, so a code file carries no prose.\n"
        "Remove the comment, or move the fact it carries into the record, a README or a\n"
        "test name. A directive a tool reads (noqa, nosec, type: ignore, a shebang) is\n"
        "never reported here, so anything above is prose.\n"
        "To strip them all:\n"
        "  uv run --no-project python .basicly/core/kit/comments/cli.py fix <path>\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
