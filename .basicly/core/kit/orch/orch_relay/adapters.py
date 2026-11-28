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
CAPABILITIES = ("names_session", "resumes_read_only", "read_only", "lane_edits")
METHODS = ("argv", "reply", "resume_command")
NEEDS = {
    "read_only": ("run a read-only turn", "run it without --read-only"),
    "lane_edits": ("edit in a lane", "run it with --read-only"),
    "resumes_read_only": (
        "resume a read-only session read-only",
        "start a new one with --read-only",
    ),
}
LOAD_ERRORS = (ImportError, AttributeError, TypeError, ValueError, OSError, RuntimeError)


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


@dataclass(frozen=True)
class Capabilities:
    names_session: bool
    resumes_read_only: bool
    read_only: bool
    lane_edits: bool

    def shown(self) -> str:
        return " ".join(name for name in CAPABILITIES if getattr(self, name)) or "none"


class Adapter(Protocol):
    name: str
    capabilities: Capabilities

    def argv(self, turn: Turn) -> list[str]: ...

    def reply(self, done: runner.Done, turn: Turn) -> Reply: ...

    def resume_command(self, session: str) -> str: ...


def _model(turn: Turn, flag: str) -> list[str]:
    return [flag, turn.model] if turn.model else []


class Claude:
    name = "claude"
    capabilities = Capabilities(True, True, True, True)

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
    capabilities = Capabilities(False, False, True, True)

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
    capabilities = Capabilities(True, True, True, True)

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


@dataclass(frozen=True)
class Entry:
    origin: str
    adapter: Adapter | None = None
    refused: str = ""


def _origin(point: importlib.metadata.EntryPoint) -> str:
    dist = getattr(point, "dist", None)
    return f"plugin {dist.name}" if dist is not None else f"plugin {getattr(point, 'value', '?')}"


def _made(point: importlib.metadata.EntryPoint) -> Adapter:
    loaded = point.load()
    made = loaded() if isinstance(loaded, type) else loaded
    missing = [method for method in METHODS if not callable(getattr(made, method, None))]
    if not isinstance(getattr(made, "capabilities", None), Capabilities):
        missing.append("capabilities")
    if missing:
        raise TypeError(f"the adapter lacks {', '.join(missing)}")
    return made


def _plugins() -> dict[str, Entry]:
    found: dict[str, Entry] = {}
    for point in importlib.metadata.entry_points(group=ENTRY_POINTS):
        if point.name in BUILTIN:
            continue
        origin = _origin(point)
        try:
            found[point.name] = Entry(origin, _made(point))
        except LOAD_ERRORS as error:
            found[point.name] = Entry(origin, refused=f"{type(error).__name__}: {error}")
    return found


def entries() -> dict[str, Entry]:
    return {**{name: Entry("built-in", made) for name, made in BUILTIN.items()}, **_plugins()}


def registry() -> dict[str, Adapter]:
    return {name: e.adapter for name, e in entries().items() if e.adapter is not None}


def adapter(name: str) -> Adapter:
    known = entries()
    found = known.get(name)
    if found is None:
        listed = [n for n in ORDER if n in known] + sorted(set(known) - set(ORDER))
        raise RefusedError(
            f"orch delegate has no adapter for the coding agent {name!r}; use one of: "
            f"{', '.join(listed)}, or install a plugin in the entry point group {ENTRY_POINTS}"
        )
    if found.adapter is None:
        raise RefusedError(
            f"orch delegate refuses the plugin {name!r} ({found.origin}) of the entry point "
            f"group {ENTRY_POINTS}: {found.refused}; fix or uninstall that package"
        )
    return found.adapter


def require(name: str, made: Adapter, capability: str) -> None:
    if not getattr(made.capabilities, capability):
        what, remedy = NEEDS[capability]
        raise RefusedError(
            f"orch delegate: {name} cannot {what}, because its adapter does not declare "
            f"the capability {capability}; {remedy}"
        )


def listing() -> list[str]:
    lines = []
    for name, found in entries().items():
        shown = found.adapter.capabilities.shown() if found.adapter else f"refused: {found.refused}"
        lines.append(f"{name}  {found.origin}  {shown}")
    return lines


def usage_limit(vendor: str, done: runner.Done) -> UsageLimitError | None:
    text = f"{done.err}\n{done.out}"
    if not LIMIT.search(text):
        return None
    reset = RESET.search(text)
    when = f"; it resets {reset.group(1).strip()}" if reset else ""
    return UsageLimitError(f"usage limit: {vendor} refused the turn at its usage limit{when}")


def lane_path(repo: Path, lane: str) -> Path:
    return repo.parent / f"{repo.name}.worktrees" / lane
