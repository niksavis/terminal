from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import segment_tokens, split_pipeline_segments, strip_heredocs

BLOCK_EXIT_CODE = 2

_GIT_VALUE_FLAGS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_STASH_READS = frozenset({"list", "show"})
_CLEAN_DRY = re.compile(r"^-[A-Za-z]*n[A-Za-z]*$")
_APPROVAL = re.compile(
    r"^BASICLY_APPROVAL=([a-z][a-z0-9]*-[a-z0-9.]+)@(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z)$"
)
APPROVAL_AGE = timedelta(minutes=60)


def _git_words(tokens: list[str]) -> list[str]:
    rest = tokens[1:]
    while rest and rest[0].startswith("-"):
        rest = rest[2:] if rest[0] in _GIT_VALUE_FLAGS else rest[1:]
    return rest


def _restores_files(args: list[str]) -> bool:
    staged = any(arg in {"--staged", "-S"} for arg in args)
    return not staged or any(arg in {"--worktree", "-W"} for arg in args)


_RULES = {
    "checkout": lambda args: "--" in args,
    "restore": _restores_files,
    "stash": lambda args: not args or args[0] not in _STASH_READS,
    "reset": lambda args: "--hard" in args,
    "clean": lambda args: not any(arg == "--dry-run" or _CLEAN_DRY.match(arg) for arg in args),
}


def _discards(words: list[str]) -> bool:
    rule = _RULES.get(words[0]) if words else None
    return bool(rule and rule(words[1:]))


def approval_of(tokens: list[str], now: datetime) -> str | None:
    for token in tokens:
        match = _APPROVAL.match(token)
        if match is None:
            continue
        stamp = match[2] if match[2].count(":") == 2 else match[2].replace("Z", ":00Z")
        given = datetime.fromisoformat(stamp)
        if timedelta(minutes=-5) <= now - given <= APPROVAL_AGE:
            return f"{match[1]}@{match[2]}"
    return None


def discarding(command: str, now: datetime | None = None) -> list[tuple[str, str | None]]:
    found = []
    moment = now or datetime.now(UTC)
    for segment in split_pipeline_segments(strip_heredocs(command)):
        tokens = segment_tokens(segment)
        assigned = []
        while tokens and re.match(r"^[A-Za-z_]\w*=", tokens[0]):
            assigned.append(tokens[0])
            tokens = tokens[1:]
        if tokens and Path(tokens[0]).name == "git" and _discards(_git_words(tokens)):
            found.append((segment.strip(), approval_of(assigned, moment)))
    return found


def _log(cwd: str, approval: str, command: str) -> bool:
    for folder in [Path(cwd), *Path(cwd).parents]:
        usage = folder / ".basicly" / "usage"
        if (folder / ".basicly").is_dir():
            usage.mkdir(exist_ok=True)
            entry = {"at": datetime.now(UTC).isoformat(), "approval": approval, "command": command}
            with (usage / "approvals.jsonl").open("a", encoding="utf-8") as out:
                out.write(json.dumps(entry) + "\n")
            return True
    return False


_ADVICE = (
    "this discards uncommitted work and is an ask-first item; undo your own edit by "
    "editing the file back, or ask the Orchestrator. After an approval, name it as a prefix "
    "of the same command: BASICLY_APPROVAL=<record>@<entry stamp, UTC, under 60 minutes "
    "old> git ...; the use is logged to .basicly/usage/approvals.jsonl. The owner can run "
    "it himself with ! <command>. Reading forms pass: git restore --staged, git stash "
    "list, git stash show, git clean -n."
)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    if not isinstance(payload, dict) or str(payload.get("tool_name", "")).lower() != "bash":
        return 0
    args = payload.get("tool_input") or {}
    command = args.get("command") if isinstance(args, dict) else None
    if not isinstance(command, str):
        return 0
    found = discarding(command)
    refused = [segment for segment, approval in found if approval is None]
    if refused:
        print(f"discard-guard: refusing {refused[0]!r}: {_ADVICE}", file=sys.stderr)
        return BLOCK_EXIT_CODE
    cwd = str(payload.get("cwd") or ".")
    for segment, approval in found:
        if approval is not None and not _log(cwd, approval, segment):
            print("discard-guard: cannot log the approval; no .basicly folder", file=sys.stderr)
            return BLOCK_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())
