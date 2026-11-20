from __future__ import annotations

import difflib
import importlib.util
import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import runner

MARKER = "orch-lessons-root"
LOG = "lessons.jsonl"
SCANNER = Path(".basicly/core/hooks/secret-scan.py")
ROOT_ENV = "ORCH_LESSONS_ROOT"
MEMBER_ENV = "ORCH_MEMBER"
STALE_AFTER = timedelta(days=14)
SESSION_END = "session-end"
SCOPES = ("local", "basicly")

Clock = Callable[[], datetime]


class RefusedError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Lesson:
    id: str
    time: datetime
    member: str
    what: str
    requirement: str
    enforcement: str
    record: str
    closed_by: str | None
    scope: str | None = None


def repo_root(start: Path) -> Path:
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    raise RefusedError(f"no git repository above {start}; run orch inside the repository")


def scanner(repo: Path) -> Callable[[str], str | None]:
    path = repo / SCANNER
    if not path.is_file():
        raise RefusedError(
            f"{SCANNER} is missing in {repo}; a lesson is written only after the repository's "
            "secret scanner checks it. Install the basicly hooks, then run the command again"
        )
    spec = importlib.util.spec_from_file_location("orch_secret_scan", path)
    if spec is None or spec.loader is None:
        raise RefusedError(f"{SCANNER} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.rule_hit


def find_root(start: Path, environ: dict[str, str]) -> Path:
    named = environ.get(ROOT_ENV, "")
    candidates = (
        [Path(named)]
        if named
        else [f / ".orchestrator" / "lessons" for f in (start, *start.parents)]
    )
    for folder in candidates:
        if (folder / MARKER).is_file():
            return folder
    raise RefusedError(
        f"no lessons folder found; run: orch lessons init <folder>, or set {ROOT_ENV}"
    )


def init(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MARKER).write_text("", encoding="utf-8")
    return folder


def member(environ: dict[str, str]) -> str:
    name = environ.get(MEMBER_ENV, "").strip()
    if not name:
        raise RefusedError(
            f"set {MEMBER_ENV} to this session's member name; the tool stamps it on each lesson"
        )
    return name


def check_text(scan: Callable[[str], str | None], texts: list[str]) -> None:
    for text in texts:
        for line in text.splitlines() or [text]:
            rule = scan(line)
            if rule is not None:
                raise RefusedError(
                    f"the secret scanner flags this text ({rule}); reword it, then add the lesson"
                )


def append(root: Path, event: dict[str, object]) -> None:
    with (root / LOG).open("a", encoding="utf-8") as log:
        log.write(json.dumps(event, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class Writer:
    root: Path
    scan: Callable[[str], str | None]
    member: str
    clock: Clock = utc_now

    def add(
        self, what: str, requirement: str, enforcement: str, record: str, scope: str | None
    ) -> str:
        if scope not in SCOPES:
            raise RefusedError(
                "a lesson needs --scope local or --scope basicly: basicly when its fix "
                "changes a file that basicly install writes, local otherwise"
            )
        check_text(self.scan, [what, requirement, enforcement, record])
        lesson_id = secrets.token_hex(4)
        append(
            self.root,
            {
                "event": "add",
                "id": lesson_id,
                "time": self.clock().isoformat(timespec="seconds"),
                "member": self.member,
                "what": what,
                "requirement": requirement,
                "enforcement": enforcement,
                "record": record,
                "scope": scope,
            },
        )
        return lesson_id

    def end_session(self) -> int:
        added = lessons_since_last_end(self.root, self.member)
        if added == 0:
            raise RefusedError(
                f"{self.member} wrote no lesson in this session; record each lesson with "
                "orch lesson add --scope local|basicly, then run orch lessons end-session again"
            )
        stamp = self.clock().isoformat(timespec="seconds")
        append(
            self.root,
            {"event": SESSION_END, "time": stamp, "member": self.member, "lessons": added},
        )
        return added

    def close(self, lesson_id: str, change: str) -> None:
        if lesson_id not in {lesson.id for lesson in lessons(self.root)}:
            raise RefusedError(
                f"no lesson {lesson_id!r}; list them with: orch lessons export --out -"
            )
        check_text(self.scan, [change])
        stamp = self.clock().isoformat(timespec="seconds")
        event = {"event": "close", "id": lesson_id, "time": stamp, "member": self.member}
        append(self.root, {**event, "change": change})

    def scope(self, lesson_id: str, scope: str) -> None:
        if lesson_id not in {lesson.id for lesson in lessons(self.root)}:
            raise RefusedError(
                f"no lesson {lesson_id!r}; list them with: orch lessons export --out -"
            )
        if scope not in SCOPES:
            raise RefusedError(
                "a lesson scope is local or basicly: basicly when its fix changes a file that "
                "basicly install writes, local otherwise"
            )
        stamp = self.clock().isoformat(timespec="seconds")
        event = {"event": "scope", "id": lesson_id, "time": stamp, "member": self.member}
        append(self.root, {**event, "scope": scope})


def unscoped(root: Path) -> list[str]:
    return [
        lesson.id for lesson in lessons(root) if lesson.closed_by is None and lesson.scope is None
    ]


def lessons(root: Path) -> list[Lesson]:
    path = root / LOG
    if not path.exists():
        return []
    found: dict[str, Lesson] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("event") == "add":
            found[event["id"]] = Lesson(
                event["id"],
                datetime.fromisoformat(event["time"]),
                event["member"],
                event["what"],
                event["requirement"],
                event["enforcement"],
                event["record"],
                None,
                event.get("scope"),
            )
        elif event.get("event") == "scope" and event.get("id") in found:
            old = found[event["id"]]
            found[event["id"]] = Lesson(**{**old.__dict__, "scope": event["scope"]})
        elif event.get("event") == "close" and event.get("id") in found:
            old = found[event["id"]]
            found[event["id"]] = Lesson(**{**old.__dict__, "closed_by": event["change"]})
    return list(found.values())


def events(root: Path) -> list[dict[str, object]]:
    path = root / LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def lessons_since_last_end(root: Path, member: str) -> int:
    added = 0
    for event in events(root):
        if event.get("member") != member:
            continue
        if event.get("event") == SESSION_END:
            added = 0
        elif event.get("event") == "add":
            added += 1
    return added


def empty_session_ends(root: Path) -> list[dict[str, object]]:
    return [
        event
        for event in events(root)
        if event.get("event") == SESSION_END and not event.get("lessons")
    ]


def export(root: Path, scan: Callable[[str], str | None], target: Path, relative: str) -> str:
    open_lessons = [
        lesson for lesson in lessons(root) if lesson.closed_by is None and lesson.scope == "basicly"
    ]
    added = [
        f"- {lesson.requirement} Enforced by: {lesson.enforcement}\n" for lesson in open_lessons
    ]
    check_text(scan, added)
    before = target.read_text(encoding="utf-8").splitlines(keepends=True) if target.exists() else []
    if before and not before[-1].endswith("\n"):
        before[-1] += "\n"
    return "".join(difflib.unified_diff(before, before + added, f"a/{relative}", f"b/{relative}"))


def stale(root: Path, clock: Clock = utc_now) -> list[Lesson]:
    now = clock()
    return [
        lesson
        for lesson in lessons(root)
        if lesson.closed_by is None and now - lesson.time > STALE_AFTER
    ]


def environ() -> dict[str, str]:
    return runner.environ()
