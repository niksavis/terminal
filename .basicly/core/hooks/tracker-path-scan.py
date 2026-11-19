from __future__ import annotations

import getpass
import importlib.util
import json
import re
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any

_TRACKER_GLOB = re.compile(r"^\.basicly/ledger/events-.*\.jsonl$")

_PATH_TAIL = r"[^\s\"'`,;)\]}]*"

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("posix-home-path", re.compile(rf"/(?:home|Users)/[A-Za-z0-9._-]+{_PATH_TAIL}")),
    ("windows-unc-path", re.compile(rf"\\\\\?\\[A-Za-z]:\\{_PATH_TAIL}")),
    ("windows-drive-path", re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s\"'`,;)\]}]+")),
)

_IDENTITY_RULE = "machine-username"
_MIN_IDENTITY_LENGTH = 4
_FIELD_KIND = "field"
_CREATED_KIND = "created"
_HOLDER_FIELD = "assignee"


def _harness(module: Any) -> Any:
    factory = getattr(module, "harness", None)
    if not callable(factory):
        raise ImportError(
            "the tracker kit lacks vault harness support; reinstall with `basicly install --force`"
        )
    return factory()


def vault_ledger() -> Path | None:
    root = Path.cwd()
    if not (
        (root / ".basicly-tracker.toml").exists()
        or (root / ".basicly/ledger").is_file()
        or (root / ".basicly/ledger-archive").exists()
    ):
        return None
    source = Path(__file__).resolve().parent.parent / "kit/tracker/locate.py"
    if not source.is_file():
        raise ImportError("the tracker kit is missing; reinstall with `basicly install --force`")
    spec = importlib.util.spec_from_file_location("basicly_tracker_kit_locate", source)
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit is missing; reinstall basicly")
    module: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return _harness(module).harness_ledger(root, time.time)


def identity_pattern() -> re.Pattern[str] | None:

    try:
        name = getpass.getuser()
    except KeyError, OSError:
        return None
    if len(name) < _MIN_IDENTITY_LENGTH:
        return None
    return re.compile(rf"\b{re.escape(name)}\b")


def staged_tracker_files() -> list[str]:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return [line for line in proc.stdout.splitlines() if _TRACKER_GLOB.match(line)]


def staged_content(path: str) -> str:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "show", f":{path}"], capture_output=True, text=True, encoding="utf-8", check=False
    )
    return proc.stdout if proc.returncode == 0 else ""


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _holder_key(event: object) -> str | None:
    if not isinstance(event, dict) or not isinstance(payload := event.get("payload"), dict):
        return None
    if event.get("kind") == _FIELD_KIND and payload.get("name") == _HOLDER_FIELD:
        return "value"
    if event.get("kind") == _CREATED_KIND and _HOLDER_FIELD in payload:
        return _HOLDER_FIELD
    return None


def _outside_holder(event: object) -> object:
    key = _holder_key(event)
    if key is None or not isinstance(event, dict):
        return event
    return {**event, "payload": {k: v for k, v in event["payload"].items() if k != key}}


def rule_hit(
    texts: list[str],
    identity: re.Pattern[str] | None = None,
    named: list[str] | None = None,
) -> str | None:
    for rule, pattern in _RULES:
        if any(pattern.search(text) for text in texts):
            return rule
    checked = texts if named is None else named
    if identity is not None and any(identity.search(text) for text in checked):
        return _IDENTITY_RULE
    return None


def findings(path: str, content: str) -> list[tuple[str, int, str]]:
    identity = identity_pattern()
    hits: list[tuple[str, int, str]] = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = line
        texts = _strings(event)
        if rule := rule_hit(texts, identity, _strings(_outside_holder(event))):
            hits.append((path, lineno, rule))
    return hits


def main() -> int:
    try:
        vault = vault_ledger()
    except (ValueError, OSError, ImportError) as exc:
        print(f"tracker-path-scan: {exc}", file=sys.stderr)
        return 1
    hits = (
        [
            finding
            for path in sorted(vault.glob("*.jsonl"))
            for finding in findings(f"vault/{path.name}", path.read_text(encoding="utf-8"))
        ]
        if vault is not None
        else [
            finding
            for path in staged_tracker_files()
            for finding in findings(path, staged_content(path))
        ]
    )
    if not hits:
        return 0
    print(
        "tracker-path-scan: machine-specific path(s) or username in staged tracker "
        "state — commit blocked.",
        file=sys.stderr,
    )
    for path, lineno, rule in hits[:20]:
        print(f"  {path}:{lineno}: {rule}", file=sys.stderr)
    if len(hits) > 20:
        print(f"  … and {len(hits) - 20} more", file=sys.stderr)
    if vault is not None:
        print(
            "Repair the vault input through the tracker; preserve the frozen ledger and archive.",
            file=sys.stderr,
        )
        return 1
    print(
        "The log is committed and cloned by every consumer, so an absolute path or "
        "username in it is published.\n"
        "Repair it with:  basicly tracker scrub\n"
        "(prefix that with `uv run` or with your `uvx --from <pin>` when basicly is not "
        "on PATH), then re-stage .basicly/ledger.\n"
        "A harness loop advance repairs it automatically.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
