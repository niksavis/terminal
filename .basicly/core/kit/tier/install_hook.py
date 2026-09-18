from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOOK_FILENAME = "claude_tier_hook.py"

CLAUDE_SETTINGS = Path(".claude") / "settings.json"

CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
USER_CONFIG_DIRNAME = ".claude"

HOOK_EVENT = "PreToolUse"
HOOK_MATCHER = "Agent"
HOOKS_KEY = "hooks"

PROJECT_DIR_PLACEHOLDER = "${CLAUDE_PROJECT_DIR}"

DEFAULT_INTERPRETER = "uv run --no-project --no-python-downloads python"

CANNOT_INTERCEPT = {
    "copilot": (
        "this kit wires no copilot spawn yet. That host selects a subagent's model in "
        "configuration rather than through a hook, so a declared tier is projected into "
        ".github/agents and nothing there reads it. Claude is wired and works"
    ),
}

HOSTS = ("claude", *sorted(CANNOT_INTERCEPT))

RESTART_NOTICE = (
    "if this wrote the first hook or agent into a directory the host did not already "
    "have, quit and relaunch the CLI process - a later edit reloads on its own, and "
    "clearing the conversation is not the same thing"
)


def hook_command(
    hook_path: Path,
    interpreter: str | None = None,
    *,
    root: Path | None = None,
    user: bool = False,
) -> str:

    if user:
        python = Path(interpreter or sys.executable).as_posix()
        return f'"{python}" "{Path(hook_path).resolve().as_posix()}"'
    script = f"{PROJECT_DIR_PLACEHOLDER}/{_within(hook_path, root)}"
    return f'{interpreter or DEFAULT_INTERPRETER} "{script}"'


def _within(hook_path: Path, root: Path | None) -> str:

    if root is None:
        raise ValueError("a project-scope command needs the repository it is written into")
    resolved = Path(hook_path).resolve()
    try:
        return resolved.relative_to(Path(root).resolve()).as_posix()
    except ValueError as error:
        raise ValueError(
            f"{resolved} is outside {Path(root).resolve()}, so no project-relative command "
            f"can name it; install with --user, or copy the kit into the repository"
        ) from error


def settings_path(root: Path, *, user: bool) -> Path:
    if not user:
        return Path(root) / CLAUDE_SETTINGS
    configured = os.environ.get(CONFIG_DIR_ENV, "").strip()
    base = Path(configured) if configured else Path.home() / USER_CONFIG_DIRNAME
    return base / CLAUDE_SETTINGS.name


def load_settings(path: Path) -> dict:

    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise ValueError(f"{path} is not valid JSON ({error}); refusing to overwrite it") from error
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} does not contain a JSON object; refusing to overwrite it")
    return parsed


def _runs_our_hook(group: object) -> bool:

    if not isinstance(group, dict):
        return False
    for hook in group.get(HOOKS_KEY) or []:
        if isinstance(hook, dict):
            command = hook.get("command")
            if isinstance(command, str) and HOOK_FILENAME in command:
                return True
    return False


def merge_hook(settings: dict, command: str) -> dict:

    merged = dict(settings)
    section = merged.get(HOOKS_KEY)
    section = dict(section) if isinstance(section, dict) else {}
    existing = section.get(HOOK_EVENT)
    kept = (
        [group for group in existing if not _runs_our_hook(group)]
        if isinstance(existing, list)
        else []
    )
    kept.append({"matcher": HOOK_MATCHER, HOOKS_KEY: [{"type": "command", "command": command}]})
    section[HOOK_EVENT] = kept
    merged[HOOKS_KEY] = section
    return merged


def drop_hook(settings: dict) -> tuple[dict, bool]:

    section = settings.get(HOOKS_KEY)
    if not isinstance(section, dict):
        return settings, False
    existing = section.get(HOOK_EVENT)
    if not isinstance(existing, list):
        return settings, False
    kept = [group for group in existing if not _runs_our_hook(group)]
    if len(kept) == len(existing):
        return settings, False
    merged = dict(settings)
    trimmed = dict(section)
    if kept:
        trimmed[HOOK_EVENT] = kept
    else:
        trimmed.pop(HOOK_EVENT, None)
    if trimmed:
        merged[HOOKS_KEY] = trimmed
    else:
        merged.pop(HOOKS_KEY, None)
    return merged, True


def uninstall_claude(root: Path, *, user: bool, dry_run: bool) -> tuple[bool, bool, str]:

    path = settings_path(root, user=user)
    scope = "user" if user else "project"
    current = load_settings(path)
    updated, changed = drop_hook(current)
    if not changed:
        return True, False, f"claude: no {HOOK_EVENT}/{HOOK_MATCHER} hook of ours in {path}"
    if dry_run:
        return True, False, f"claude: would remove the {HOOK_EVENT}/{HOOK_MATCHER} hook from {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return True, True, f"claude: removed the {HOOK_EVENT}/{HOOK_MATCHER} hook ({scope}) from {path}"


def install_claude(
    root: Path, *, user: bool, dry_run: bool, interpreter: str | None = None
) -> tuple[bool, bool, str]:

    hook = Path(__file__).resolve().parent / HOOK_FILENAME
    if not hook.is_file():
        return False, False, f"claude: {hook} is missing, so there is no hook to install"
    path = settings_path(root, user=user)
    scope = "user" if user else "project"
    current = load_settings(path)
    updated = merge_hook(current, hook_command(hook, interpreter, root=root, user=user))
    if updated == current:
        return True, False, f"claude: already installed ({scope} scope) in {path}"
    if dry_run:
        return True, False, f"claude: would write the {HOOK_EVENT}/{HOOK_MATCHER} hook to {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return (
        True,
        True,
        f"claude: wrote the {HOOK_EVENT}/{HOOK_MATCHER} hook ({scope} scope) to {path}",
    )


def install(
    hosts: list[str],
    root: Path,
    *,
    user: bool,
    dry_run: bool,
    interpreter: str | None = None,
) -> tuple[bool, list[str]]:

    lines = []
    installed = False
    wrote = False
    for host in hosts:
        reason = CANNOT_INTERCEPT.get(host)
        if reason is not None:
            lines.append(f"{host}: nothing installed - {reason}")
            continue
        ok, written, message = install_claude(
            root, user=user, dry_run=dry_run, interpreter=interpreter
        )
        installed = installed or ok
        wrote = wrote or written
        lines.append(message)
    if wrote:
        lines.append(RESTART_NOTICE)
    return installed, lines


def uninstall(hosts: list[str], root: Path, *, user: bool, dry_run: bool) -> tuple[bool, list[str]]:

    lines = []
    removed = False
    for host in hosts:
        reason = CANNOT_INTERCEPT.get(host)
        if reason is not None:
            lines.append(f"{host}: nothing removed - {reason}")
            continue
        ok, _, message = uninstall_claude(root, user=user, dry_run=dry_run)
        removed = removed or ok
        lines.append(message)
    return removed, lines


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the tier injection hook into a coding agent's settings."
    )
    parser.add_argument(
        "--host",
        action="append",
        choices=HOSTS,
        help="host to install for; repeatable (default: every known host)",
    )
    parser.add_argument(
        "--user",
        action="store_true",
        help="install for every repository on this machine instead of just this one",
    )
    parser.add_argument("--root", help="repository to install into (default: cwd)")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="remove the hook this script installs, leaving every other hook alone",
    )
    parser.add_argument(
        "--interpreter",
        help=(
            "command that runs the hook script, for a consumer without uv "
            f"(default at project scope: {DEFAULT_INTERPRETER!r}; "
            "at user scope, the interpreter running this installer)"
        ),
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be written and write nothing"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:

    args = _parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()
    try:
        hosts = list(args.host or HOSTS)
        if args.uninstall:
            installed, lines = uninstall(hosts, root, user=args.user, dry_run=args.dry_run)
        else:
            installed, lines = install(
                hosts,
                root,
                user=args.user,
                dry_run=args.dry_run,
                interpreter=args.interpreter,
            )
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    if not installed:
        print("nothing was removed" if args.uninstall else "nothing was installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
