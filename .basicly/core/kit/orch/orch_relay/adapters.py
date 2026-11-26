from __future__ import annotations

import importlib.metadata
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from orch_lessons.log import RefusedError

if TYPE_CHECKING:
    import runner

ENTRY_POINTS = "basicly_orch.adapters"
ORDER = ("claude", "codex", "copilot")
LIMIT = re.compile(
    r"usage limit|rate limit|quota (?:exceeded|exhausted)|limit reached|too many requests|\b429\b",
    re.IGNORECASE,
)
RESET = re.compile(
    r"(?:resets?|try again|available again)\s+(?:at|in|after|on)\s+([^\n.\"]{1,60})", re.IGNORECASE
)


COPILOT_SHELL = ("git status", "git diff", "git add", "git commit", "uv run", "pytest")
COPILOT_DENY = ("shell(git push)", "shell(git reset)", "shell(git checkout)", "shell(rm)", "url")
FORBIDDEN = (
    "--allow-all",
    "--allow-all-tools",
    "--allow-all-paths",
    "--allow-all-urls",
    "--yolo",
    "--autopilot",
    "--dangerously-skip-permissions",
    "--dangerously-bypass-approvals-and-sandbox",
)
RULE_FLAGS = ("--allow-tool=", "--deny-tool=", "--disallow-temp-dir")


class UsageLimitError(RefusedError):
    pass


@dataclass(frozen=True)
class Turn:
    prompt: str
    session: str | None
    resume: bool
    model: str | None = None
    read_only: bool = False
    lane: str | None = None


@dataclass(frozen=True)
class Reply:
    text: str
    session: str


class Adapter(Protocol):
    name: str
    names_session: bool
    resumes_read_only: bool

    def argv(self, turn: Turn) -> list[str]: ...

    def reply(self, done: runner.Done, turn: Turn) -> Reply: ...

    def resume_command(self, session: str) -> str: ...


def _model(turn: Turn, flag: str) -> list[str]:
    return [flag, turn.model] if turn.model else []


class Claude:
    name = "claude"
    names_session = True
    resumes_read_only = True

    def argv(self, turn: Turn) -> list[str]:
        session = ["--resume" if turn.resume else "--session-id", str(turn.session)]
        mode = ["--permission-mode", "plan" if turn.read_only else "acceptEdits"]
        head = ["claude", "-p", turn.prompt, "--output-format", "json"]
        return [*head, *mode, *_model(turn, "--model"), *session]

    def reply(self, done: runner.Done, turn: Turn) -> Reply:
        try:
            shown = json.loads(done.out)
        except ValueError as error:
            raise RefusedError(f"claude printed no JSON result: {done.out[:300]!r}") from error
        result = shown.get("result") if isinstance(shown, dict) else None
        if not isinstance(result, str) or shown.get("is_error"):
            raise RefusedError(f"claude ended without an answer: {done.out[:300]!r}")
        return Reply(result, str(shown.get("session_id") or turn.session))

    def resume_command(self, session: str) -> str:
        return f"claude --resume {session}"


class Codex:
    name = "codex"
    names_session = False
    resumes_read_only = False

    def argv(self, turn: Turn) -> list[str]:
        model = _model(turn, "-m")
        if turn.resume:
            return ["codex", "exec", "resume", "--json", *model, str(turn.session), turn.prompt]
        sandbox = "read-only" if turn.read_only else "workspace-write"
        return ["codex", "exec", "--json", "-s", sandbox, *model, turn.prompt]

    def reply(self, done: runner.Done, turn: Turn) -> Reply:
        session, text = turn.session, None
        for line in done.out.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            session = str(event.get("thread_id") or event.get("session_id") or session or "")
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message":
                text = str(item.get("text", ""))
        if not text or not session:
            raise RefusedError(
                f"codex printed no agent message or no thread id: {done.out[-300:]!r}"
            )
        return Reply(text, session)

    def resume_command(self, session: str) -> str:
        return f"codex resume {session}"


def _lane_rules(lane: str | None) -> list[str]:
    if lane is None:
        return []
    allow = [f"--allow-tool=write({lane}/**)"]
    allow += [f"--allow-tool=shell({command})" for command in COPILOT_SHELL]
    deny = [f"--deny-tool={rule}" for rule in COPILOT_DENY]
    return [*allow, *deny, "--disallow-temp-dir"]


def refuse_bypass(vendor: str, argv: list[str]) -> None:
    found = [part for part in argv if part.split("=", 1)[0] in FORBIDDEN]
    if found:
        raise RefusedError(
            f"orch delegate never passes {', '.join(found)} to {vendor}; "
            f"fix the adapter so the agent works inside its lane rules"
        )


def rules(argv: list[str]) -> list[str]:
    return [part for part in argv if part.startswith(RULE_FLAGS)]


class Copilot:
    name = "copilot"
    names_session = True
    resumes_read_only = True

    def argv(self, turn: Turn) -> list[str]:
        session = f"--resume={turn.session}" if turn.resume else f"--session-id={turn.session}"
        rules = ["--deny-tool=write"] if turn.read_only else _lane_rules(turn.lane)
        return ["copilot", "-p", turn.prompt, "--silent", *rules, *_model(turn, "--model"), session]

    def reply(self, done: runner.Done, turn: Turn) -> Reply:
        if not done.out.strip():
            raise RefusedError("copilot printed no answer")
        return Reply(done.out.strip(), str(turn.session))

    def resume_command(self, session: str) -> str:
        return f"copilot --resume={session}"


BUILTIN: dict[str, Adapter] = {"claude": Claude(), "codex": Codex(), "copilot": Copilot()}


def _plugins() -> dict[str, Adapter]:
    found: dict[str, Adapter] = {}
    for point in importlib.metadata.entry_points(group=ENTRY_POINTS):
        if point.name in BUILTIN:
            continue
        loaded = point.load()
        found[point.name] = loaded() if isinstance(loaded, type) else loaded
    return found


def registry() -> dict[str, Adapter]:
    return {**BUILTIN, **_plugins()}


def adapter(name: str) -> Adapter:
    known = registry()
    if name not in known:
        listed = [n for n in ORDER if n in known] + sorted(set(known) - set(ORDER))
        raise RefusedError(
            f"orch delegate has no adapter for the coding agent {name!r}; use one of: "
            f"{', '.join(listed)}, or install a plugin in the entry point group {ENTRY_POINTS}"
        )
    return known[name]


def usage_limit(vendor: str, done: runner.Done) -> UsageLimitError | None:
    text = f"{done.err}\n{done.out}"
    if not LIMIT.search(text):
        return None
    reset = RESET.search(text)
    when = f"; it resets {reset.group(1).strip()}" if reset else ""
    return UsageLimitError(f"usage limit: {vendor} refused the turn at its usage limit{when}")


def lane_path(repo: Path, lane: str) -> Path:
    return repo.parent / f"{repo.name}.worktrees" / lane
