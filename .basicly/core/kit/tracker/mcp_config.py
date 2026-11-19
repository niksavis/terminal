from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _launcher(args: argparse.Namespace, repository: Path) -> tuple[str, list[str]]:
    target = str(repository) if args.scope == "user" else "."
    command, argv = "basicly-tracker", ["mcp", "--repository", target]
    bundle = args.bundle
    python = args.python or ("python" if sys.platform == "win32" else "python3")
    if args.runner == "package" and bundle is None and args.python is not None:
        raise ValueError("--python needs --runner kit or a bundle launcher.")
    if args.runner == "kit" and bundle is None:
        script = Path(__file__).resolve().with_name("mcp_server.py")
        if args.scope == "user":
            command, argv = args.python or sys.executable, [str(script), "--repository", target]
        else:
            local = repository / ".basicly/core/kit/tracker/mcp_server.py"
            if not local.is_file():
                raise ValueError("Project kit registration needs its installed MCP adapter.")
            command, argv = (
                python,
                [".basicly/core/kit/tracker/mcp_server.py", "--repository", target],
            )
    if bundle is not None:
        if not bundle.is_file():
            raise ValueError(
                "The requested bundle is missing. Run the standalone init --sandbox first."
            )
        if args.scope == "user":
            command, script = args.python or sys.executable, str(bundle.resolve())
        else:
            command = python
            try:
                script = bundle.resolve().relative_to(repository).as_posix()
            except ValueError as exc:
                raise ValueError(
                    "Project registration needs a repository bundle. Run init --sandbox."
                ) from exc
        argv = [script, *argv]
    if not command or "\0" in command:
        raise ValueError("--python must name an interpreter executable.")
    return command, argv


def configuration(args: argparse.Namespace) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", args.name):
        raise ValueError("--name must use letters, digits, underscores or hyphens.")
    repository = args.repository.resolve(strict=True)
    if not repository.is_dir() or not (repository / ".git").exists():
        raise ValueError("--repository must name a Git working tree root.")
    command, argv = _launcher(args, repository)
    server = {"command": command, "args": argv}
    if args.client == "codex":
        lines = [
            f"[mcp_servers.{args.name}]",
            f"command = {json.dumps(command, ensure_ascii=False)}",
            f"args = {json.dumps(argv, ensure_ascii=False)}",
            'env_vars = ["BASICLY_TRACKER_SESSION", "BASICLY_HOLDER", '
            '"BASICLY_TRACKER_STATE", "XDG_STATE_HOME", "LOCALAPPDATA"]',
            f"[mcp_servers.{args.name}.env]",
            'AI_AGENT = "codex"',
        ]
        document = "\n".join(lines) + "\n"
        path = "~/.codex/config.toml" if args.scope == "user" else ".codex/config.toml"
    else:
        document = (
            json.dumps(
                {
                    "mcpServers": {
                        args.name: {
                            "type": "stdio",
                            **server,
                            "env": {
                                "BASICLY_TRACKER_SESSION": "${BASICLY_TRACKER_SESSION}",
                                "BASICLY_HOLDER": "${BASICLY_HOLDER:-}",
                                "BASICLY_TRACKER_STATE": "${BASICLY_TRACKER_STATE:-}",
                                "XDG_STATE_HOME": "${XDG_STATE_HOME:-}",
                                "LOCALAPPDATA": "${LOCALAPPDATA:-}",
                                "AI_AGENT": "claude",
                            },
                        }
                    }
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        path = "~/.claude.json" if args.scope == "user" else ".mcp.json"
    return {
        "schema": "basicly.tracker.mcp-config.v1",
        "client": args.client,
        "scope": args.scope,
        "destination": path,
        "configuration": document,
        "written": False,
        "instructions": (
            "Merge this server entry into the destination. Preserve unrelated settings. "
            "Launch each agent with a unique tracker session."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print client registration without changing configuration."
    )
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--client", choices=("codex", "claude"), required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--name", default="basicly-tracker")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--runner", choices=("package", "kit"), default="kit")
    parser.add_argument("--python", help="The interpreter for a kit or bundle launcher.")
    args = parser.parse_args(argv)
    try:
        report = configuration(args)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"tracker: {exc}\n")
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
