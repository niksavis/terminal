from __future__ import annotations

import contextlib
import importlib.util
import io
import json
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


def _paths(argv: list[str]) -> list[str]:
    if argv != ["--paths-json-stdin"]:
        if "--paths-json-stdin" in argv:
            raise ValueError("Use --paths-json-stdin alone and send a JSON path list.")
        return argv
    paths = json.load(sys.stdin)
    if not isinstance(paths, list) or any(
        not isinstance(path, str) or not path or "\0" in path for path in paths
    ):
        raise ValueError("--paths-json-stdin requires a JSON list of nonempty paths without NUL.")
    return paths


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("no-comments: the installed comment checker is missing")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _check(policy: str, paths: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        if policy == "no-comment-ratchet":
            checker = _load(_HERE / "comment_ratchet.py", "basicly_comments_hook_ratchet")
            code = checker.main(["--", *paths], kit_root=_kit_cli().parent)
        else:
            checker = _load(_kit_cli(), "basicly_comments_hook_cli")
            code = checker.main(["check", "--", *paths])
    return int(code), out.getvalue(), err.getvalue()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    try:
        policy = comment_policy(Path.cwd())
        paths = _paths(list(argv if argv is not None else sys.argv[1:]))
        if not paths:
            return 0
        code, out, err = _check(policy, paths)
    except (OSError, ValueError) as error:
        print(f"no-comments: {error}", file=sys.stderr)
        return 1
    if code == 0:
        return 0
    sys.stdout.write(out)
    sys.stderr.write(err)
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
