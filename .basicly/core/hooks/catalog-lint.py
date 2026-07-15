"""Pre-commit hook: validate catalog YAML sources via ``basicly catalog-lint``.

Runs the CLI so the hook and the command share one implementation. Blocks a
commit that introduces a schema-invalid source, a discoverable-name source
(SKILL.md / *.fragment.md), or a stray .yml under the catalog.

The CLI is resolved through a ladder so the hook works in consumers where the
engine is not an importable package: ``basicly`` on PATH, then
``python -m basicly.cli``, then ``uvx`` from the pinned distribution source.
When no channel is available the hook warns and passes (advisory) — the
scaffolded CI workflow runs catalog-lint as the deterministic backstop.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

DIST_SOURCE = "git+https://github.com/niksavis/basicly@main"


def _cli_command() -> list[str] | None:
    """Resolve a runnable catalog-lint command, or None when unavailable."""
    basicly = shutil.which("basicly")
    if basicly:
        return [basicly, "catalog-lint"]
    if importlib.util.find_spec("basicly") is not None:
        return [sys.executable, "-m", "basicly.cli", "catalog-lint"]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", DIST_SOURCE, "basicly", "catalog-lint"]
    return None


def main() -> int:
    """Run ``basicly catalog-lint`` from the repository root."""
    command = _cli_command()
    if command is None:
        print(
            "catalog-lint skipped: basicly is not installed and uvx is unavailable; "
            "CI (basicly-gates.yml) runs this check. Install uv to gate locally.",
            file=sys.stderr,
        )
        return 0
    proc = subprocess.run(command, cwd=Path.cwd(), check=False)  # nosec B603
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
