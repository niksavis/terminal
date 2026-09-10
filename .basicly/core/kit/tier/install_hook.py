"""Install the tier injection hook into the host that will actually run it.

The deliberate opt-in step of the portable kit (basicly-wbsz.3). The two files
beside this one answer *which model* a tier means and *how* to rewrite a spawn;
this one wires the second into a host's settings, under the same constraint as
both: **no basicly**. No ``import basicly``, nothing on ``PATH``, no third-party
package, no network. A consumer who copied the kit into an unrelated project
runs this and is done.

Run it::

    python3 install_hook.py                 # this repository's own settings
    python3 install_hook.py --user          # every repository on this machine
    python3 install_hook.py --dry-run       # print what it would write

**It is asymmetric by host, and says so rather than pretending otherwise.**

- **Claude Code**: installs. A ``PreToolUse`` hook matching the ``Agent`` tool,
  written into ``.claude/settings.json`` — the repository's by default, because a
  repo-scoped harness should not change how every other project on the machine
  spawns agents. ``--user`` is the deliberate opt-in to that wider scope, and is
  safe because ``claude_tier_hook.py`` only answers for a directory tree that has
  its own committed map.

  **The two scopes are written differently, on purpose** (basicly-dukb). The
  repository's file is committed and shared, so it gets a command that names the
  hook through ``${CLAUDE_PROJECT_DIR}`` and runs it with ``uv`` — no absolute
  path, nothing machine-specific, identical on Windows, Linux and macOS. The
  user's file is machine-local, so it keeps absolute paths and needs nothing on
  ``PATH``. ``--interpreter`` overrides the command for a consumer without uv.
- **GitHub Copilot CLI**: installs **nothing**, and reports why. **Copilot does have
  hooks** — corrected 2026-08-08; the earlier "no hook surface at all" claim was an
  artifact of the probe, and this repo already ships a ``postToolUse`` hook there.
  What is unshown is the narrower thing this kit needs: a repo-level
  ``.github/hooks/*.json`` hook never fired **for an agent spawn** across three probes
  (basicly-wbsz) on 1.0.77, and GitHub documents ``preToolUse`` as able to *approve or
  deny* a tool call, where a spawn rewrite needs *modify*. Copilot's working path is
  therefore static frontmatter plus session-level ``copilot --model``. Reporting a
  successful install for a hook that will not rewrite the spawn would be worse than
  declining.

Re-running converges: a group running this kit's hook is stripped and rewritten
rather than appended, so the second run changes nothing and duplicates nothing.
Hooks the consumer wrote themselves are matched by the script they run, never by
position, and are left untouched.

**A run that writes says the host must be restarted** (basicly-e3z6). The host
reads its hooks once, at process start; clearing the conversation reloads neither
hooks nor agent definitions (measured on basicly-wbsz.3), so a consumer who stops
at this installer's success line gets no injection and every diagnostic they can
reach says the hook is installed correctly. A dry run and an already-installed
converge run do **not** say it, because nothing changed for a restart to pick up.

A ``settings.json`` that exists but cannot be parsed is **refused, never
overwritten** — it is the consumer's file and a mangled one is a worse outcome
than an uninstalled hook.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HOOK_FILENAME = "claude_tier_hook.py"

# Where each host keeps the settings this installer writes, relative to the
# scope root. Claude is the only entry today; the shape is a table rather than a
# branch so a host that grows a hook surface is a row, not a rewrite.
CLAUDE_SETTINGS = Path(".claude") / "settings.json"

# Honoured so a caller can dictate the user-level location instead of this
# module guessing it per platform — which is also what makes the user-scope path
# testable without touching the developer's own configuration.
CONFIG_DIR_ENV = "CLAUDE_CONFIG_DIR"
USER_CONFIG_DIRNAME = ".claude"

HOOK_EVENT = "PreToolUse"
HOOK_MATCHER = "Agent"
HOOKS_KEY = "hooks"

# Claude substitutes this itself, as a plain string, before any shell sees it.
# That is what makes it the one way to name a file inside the repository that is
# neither absolute nor dependent on the directory the spawn happened in - and it
# keeps working under PowerShell, where the brace form is not shell syntax.
PROJECT_DIR_PLACEHOLDER = "${CLAUDE_PROJECT_DIR}"

# uv, not a bare `python3` (owner, basicly-dukb). Every committer to a
# basicly-managed repo already needs uv on PATH because the projected git hooks
# run `uv run python`, so for a consumer this adds nothing; and Windows ships no
# `python3.exe` from the python.org installer, where the name instead hits an App
# Execution Alias that opens the Microsoft Store - a worse failure than a clean
# one. `--no-project` keeps a spawn out of virtualenv resolution, and
# `--no-python-downloads` keeps the spawn path network-free: it fails closed
# rather than fetching an interpreter mid-spawn.
DEFAULT_INTERPRETER = "uv run --no-project --no-python-downloads python"

# Hosts this kit knows about but cannot install for, and the measured reason.
# Kept as data so `--host copilot` gets an answer rather than an unknown-host
# error, which would read as "you typed it wrong" instead of "it cannot work".
CANNOT_INTERCEPT = {
    "copilot": (
        "no copilot hook is known to fire for a spawn "
        "(repo-level .github/hooks never fired across three probes, and 1.0.77 "
        "has no hooks directory, no hook setting and no hook option); use static "
        "frontmatter plus `copilot --model` instead"
    ),
}

HOSTS = ("claude", *sorted(CANNOT_INTERCEPT))

# Printed only after a run that wrote a hook, and narrower than it used to be. The old
# form said hooks and agent definitions are read once at startup (basicly-wbsz.3, no
# version pinned); refuted on claude 2.1.226, 2026-08-09 - both are watched and reload
# in seconds. What still needs a relaunch is what a first install creates: the first
# file in a scope directory the host did not have at startup.
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
    """The shell command the host runs for one spawn, rendered for its scope.

    The two scopes want opposite things, which is why this is not one rendering.

    ``~/.claude/settings.json`` is machine-local by definition, so the user scope
    keeps both halves absolute: nothing needs to be on ``PATH``, and the very
    interpreter that ran the installer is the one that runs the hook.

    A repository's ``.claude/settings.json`` is a **committed, shared** file, so
    an absolute path there leaks a username into a commit and is wrong on every
    other machine (basicly-dukb). A bare relative path is not the fix either: the
    host documents that handlers run in the *current* directory rather than the
    project root, and this repository has already watched its own relative hook
    fail once the working directory drifted. ``${CLAUDE_PROJECT_DIR}`` is what
    resolves both halves of that - Claude expands it to the project root whatever
    the working directory is.

    Every path is forward-slashed, because a backslash would be eaten by the
    shell that runs this.

    Raises:
        ValueError: when a project-scope install cannot name the hook relative to
            *root*. Refusing beats falling back to the absolute rendering, which
            is the defect this function exists to fix.
    """
    if user:
        python = Path(interpreter or sys.executable).as_posix()
        return f'"{python}" "{Path(hook_path).resolve().as_posix()}"'
    script = f"{PROJECT_DIR_PLACEHOLDER}/{_within(hook_path, root)}"
    return f'{interpreter or DEFAULT_INTERPRETER} "{script}"'


def _within(hook_path: Path, root: Path | None) -> str:
    """*hook_path* named relative to *root*, forward-slashed.

    Derived from the two paths rather than from a constant, so a consumer who
    copied the kit somewhere other than basicly's own layout still gets a command
    that resolves.
    """
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
    """The settings file to write for the requested scope."""
    if not user:
        return Path(root) / CLAUDE_SETTINGS
    configured = os.environ.get(CONFIG_DIR_ENV, "").strip()
    base = Path(configured) if configured else Path.home() / USER_CONFIG_DIRNAME
    return base / CLAUDE_SETTINGS.name


def load_settings(path: Path) -> dict:
    """The settings at *path*, or an empty mapping when there are none yet.

    Raises:
        ValueError: when the file exists but is not a JSON object. Refusing is
            the point — this is the consumer's file, and overwriting it to
            install a convenience would be the worse failure.
    """
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
    """Whether one hook group runs this kit's hook.

    Matched by the hook's filename inside the command, which is what makes a
    re-run converge. A consumer's own hook is left alone because it does not run
    this script.
    """
    if not isinstance(group, dict):
        return False
    for hook in group.get(HOOKS_KEY) or []:
        if isinstance(hook, dict):
            command = hook.get("command")
            if isinstance(command, str) and HOOK_FILENAME in command:
                return True
    return False


def merge_hook(settings: dict, command: str) -> dict:
    """Settings with this kit's hook installed exactly once.

    Strips any group already running the kit's hook and appends a fresh one, so
    the result is the same whether it is the first run or the fifth, and a
    changed interpreter path replaces the old entry instead of racing it.
    """
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


def install_claude(
    root: Path, *, user: bool, dry_run: bool, interpreter: str | None = None
) -> tuple[bool, bool, str]:
    """Install the hook for Claude Code; return ``(installed, wrote, message)``.

    ``wrote`` is narrower than ``installed`` on purpose: a dry run and an
    already-installed converge run both leave the host in a working state, but
    neither changed a file, so neither is a reason to tell someone to restart.
    """
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
    """Install for each requested host; return ``(any_installed, report lines)``.

    The restart notice is the last line, and only when some host was actually
    written to - once for the whole run rather than once per host, because it is
    the reader's next step, not a property of any one host.
    """
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
    """Install, report what happened per host, and exit non-zero if nothing did.

    The exit status is the part a script can branch on: a run that only declined
    must not look like a run that installed.
    """
    args = _parse_args(argv)
    root = Path(args.root) if args.root else Path.cwd()
    try:
        installed, lines = install(
            list(args.host or HOSTS),
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
        print("nothing was installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
