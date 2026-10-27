from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _kit_cli() -> Path:
    installed = _HERE.parent / "kit" / "comments" / "cli.py"
    if installed.exists():
        return installed
    raise SystemExit("no-comments: the comments kit is missing from beside this hook")


def comment_policy(root: Path) -> str:
    policy = "no-comments"
    for path in (
        root / "basicly.toml",
        *sorted((root / "basicly.d").glob("*.toml")),
        root / "basicly.local.toml",
    ):
        if not path.is_file():
            continue
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        if not isinstance(hooks, dict):
            raise ValueError("hooks must be a table")
        settings = hooks.get("comments", {})
        if not isinstance(settings, dict) or set(settings) - {"policy"}:
            raise ValueError("hooks.comments accepts only policy")
        policy = settings.get("policy", policy)
        if not isinstance(policy, str) or policy not in {"no-comments", "no-comment-ratchet"}:
            raise ValueError('hooks.comments.policy must be "no-comments" or "no-comment-ratchet"')
    return policy


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    try:
        policy = comment_policy(Path.cwd())
    except (OSError, ValueError) as err:
        print(f"no-comments: {err}", file=sys.stderr)
        return 1
    paths = list(argv if argv is not None else sys.argv[1:])
    if not paths:
        return 0
    command = (
        [str(_HERE / "comment_ratchet.py"), *paths]
        if policy == "no-comment-ratchet"
        else [str(_kit_cli()), "check", *paths]
    )
    completed = subprocess.run(  # nosec B603
        [sys.executable, "-X", "utf8", *command],
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
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
