from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import runner as kit_runner
from orch_relay import record
from orch_state import commands, herdr, relay_guard, reporter, store

from orch_lessons import log

CLAUDE_SETTINGS = (Path(".claude/settings.json"), Path(".claude/settings.local.json"))
PROBE = ("orch", "approve", "--request", "r")
PROBE_TEXT = " ".join(PROBE)
CLAUDE_DENY_FIX = "Bash(orch approve *)"
CODEX_DENY_FIX = 'prefix_rule(pattern=["orch", "approve"], decision="forbidden")'
COPILOT_PERMISSIONS = Path(".copilot/permissions-config.json")
RULES_DOC_ENV = "ORCH_RULES_DOC"
RULESET_ENV = "ORCH_RULESET"
BUNDLED_RULESET = Path(__file__).with_name("ruleset.json")
OWNER_LINE = re.compile(
    r'(?<!")(?:\bOwner (?:rule|answer|addition)\b|\bWorking rule\b|\(lesson\b)'
    r'(?:[^.:"]*?(\d{4}-\d{2}-\d{2}))?'
)

Runner = Callable[[list[str]], str]


@dataclass(frozen=True)
class Report:
    lines: list[str]
    failed: bool


def _stem_match(command: str, stem: str) -> bool:
    return command == stem or command.startswith(stem + " ")


def bash_rule_matches(rule: str, command: str) -> bool:
    if rule in ("Bash", "Bash(*)"):
        return True
    if not (rule.startswith("Bash(") and rule.endswith(")")):
        return False
    content = rule[5:-1]
    for suffix in (":*", " *"):
        if content.endswith(suffix):
            return _stem_match(command, content[: -len(suffix)])
    if "*" in content:
        return fnmatch.fnmatchcase(command, content)
    return command == content


def allows_orch(rule: str) -> bool:
    return bash_rule_matches(rule, PROBE_TEXT)


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise log.RefusedError(f"{path} cannot be read as JSON ({error})") from error


def _rules(path: Path, kind: str) -> list[str]:
    data = _read_json(path)
    permissions = data.get("permissions") if isinstance(data, dict) else None
    found = permissions.get(kind) if isinstance(permissions, dict) else None
    return [rule for rule in found if isinstance(rule, str)] if isinstance(found, list) else []


def settings_files(repo: Path, environ: dict[str, str]) -> list[Path]:
    files = [repo / name for name in CLAUDE_SETTINGS]
    home = environ.get("HOME", "")
    if home:
        files.append(Path(home) / ".claude" / "settings.json")
    return files


def claude_lines(files: list[Path]) -> tuple[list[str], bool]:
    denies = [(path, rule) for path in files for rule in _rules(path, "deny") if allows_orch(rule)]
    allows = [(path, rule) for path in files for rule in _rules(path, "allow") if allows_orch(rule)]
    if denies:
        path, rule = denies[0]
        return [f"claude: deny rule {rule!r} in {path} covers orch approve"], False
    return [
        f"{path}: allow rule {rule!r} lets a session run orch approve; add the deny rule "
        f"{CLAUDE_DENY_FIX!r}, which wins over every allow rule"
        for path, rule in allows
    ], bool(allows)


def run_codex(argv: list[str]) -> str:
    return kit_runner.capture(argv, 30).out


def codex_lines(
    repo: Path,
    environ: dict[str, str],
    runner: Runner = run_codex,
    find: Callable[[str, str | None], str | None] = lambda name, path: kit_runner.which(
        name, path=path
    ),
) -> tuple[list[str], bool]:
    home = environ.get("HOME", "")
    folders = [repo / ".codex" / "rules", *([Path(home) / ".codex" / "rules"] if home else [])]
    files = sorted(path for folder in folders for path in folder.glob("*.rules"))
    if not files:
        return [], False
    codex = find("codex", environ.get("PATH"))
    if codex is None:
        return ["codex rules: not checked, codex is not on PATH"], False
    argv = [codex, "execpolicy", "check"]
    for path in files:
        argv += ["--rules", str(path)]
    try:
        result = json.loads(runner([*argv, *PROBE]) or "{}")
    except ValueError:
        return ["codex rules: not checked, codex execpolicy check gave no JSON"], False
    if result.get("decision") != "allow":
        return [], False
    names = ", ".join(str(path) for path in files)
    return [
        f"codex rules {names}: they allow orch approve; add {CODEX_DENY_FIX}, "
        "the most restrictive decision wins"
    ], True


def _covers(location: str, repo: Path) -> bool:
    return repo == Path(location) or Path(location) in repo.parents


def copilot_lines(repo: Path, environ: dict[str, str]) -> tuple[list[str], bool]:
    home = environ.get("HOME", "")
    if not home:
        return [], False
    path = Path(home) / COPILOT_PERMISSIONS
    data = _read_json(path)
    locations = data.get("locations") if isinstance(data, dict) else None
    if not isinstance(locations, dict):
        return [], False
    lines = [
        f"{path}: location {location} saves an approval for {name!r}; Copilot then runs "
        "orch approve without asking; remove it"
        for location, entry in locations.items()
        if isinstance(entry, dict) and _covers(str(location), repo)
        for approval in entry.get("tool_approvals") or []
        if isinstance(approval, dict) and approval.get("kind") == "commands"
        for name in approval.get("commandIdentifiers") or []
        if isinstance(name, str) and _stem_match(PROBE_TEXT, name.removesuffix(":*"))
    ]
    return lines, bool(lines)


def _flat(text: str) -> str:
    return " ".join(text.split())


def owner_claims(ruleset: Path) -> list[tuple[str | None, str]]:
    data = _read_json(ruleset)
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        raise log.RefusedError(f"{ruleset} holds no rules list")
    return [
        (claim.get("date"), _flat(str(claim.get("phrase", ""))))
        for rule in rules
        if isinstance(rule, dict)
        for claim in rule.get("owner") or []
        if isinstance(claim, dict) and claim.get("phrase")
    ]


def rule_parity_lines(environ: dict[str, str]) -> tuple[list[str], bool]:
    named = environ.get(RULES_DOC_ENV, "")
    if not named:
        return [f"rule parity: not checked, set {RULES_DOC_ENV} to the workspace rules file"], False
    doc = Path(named)
    if not doc.is_file():
        return [f"rule parity: {RULES_DOC_ENV} names {doc}, which is not a file"], True
    ruleset = Path(environ.get(RULESET_ENV, "") or BUNDLED_RULESET)
    claims = owner_claims(ruleset)
    missing: list[str] = []
    seen = 0
    for number, text in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
        found = OWNER_LINE.search(text)
        if found is None:
            continue
        seen += 1
        flat = _flat(text)
        if not any(date == found.group(1) and phrase in flat for date, phrase in claims):
            when = found.group(1) or "no date"
            missing.append(f"{doc}:{number}: owner rule ({when}) has no entry in {ruleset}")
    summary = f"rule parity: {seen - len(missing)} of {seen} owner rules have a kit entry"
    return [*missing, summary], bool(missing)


def wake_adapter_line(environ: dict[str, str]) -> str:
    pane = herdr.pane_id(environ)
    if environ.get("HERDR_ENV") and pane and herdr.binary(environ):
        return f"wake adapter: herdr (pane {pane})"
    return "wake adapter: none; an idle interactive session gets its mail only at its next turn"


def lesson_lines(cwd: Path, environ: dict[str, str]) -> tuple[list[str], bool]:
    try:
        root = log.find_root(cwd, environ)
    except log.RefusedError as missing:
        return [f"lessons: not checked, {missing}"], False
    empty = log.empty_session_ends(root)
    flagged = [
        f"session of {event.get('member')} ended {event.get('time')} with no lesson"
        for event in empty
    ]
    old = log.stale(root)
    lines = [
        *flagged,
        *(
            f"lesson {lesson.id} open since {lesson.time.date()}: {lesson.requirement}"
            for lesson in old
        ),
    ]
    lines.append(f"lessons: {len(old)} open longer than {log.STALE_AFTER.days} days")
    return lines, bool(old) or bool(empty)


RELAY_PREFIXES = ("[approval ", "[decision ")


def _entries(tracker: record.Tracker) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for prefix in RELAY_PREFIXES:
        for name in tracker.matching(prefix.strip()):
            found.extend((name, text) for text in tracker.comments(name) if text.startswith(prefix))
    return list(dict.fromkeys(found))


def relay_lines(
    cwd: Path, environ: dict[str, str], tracker: record.Tracker | None = None
) -> tuple[list[str], bool]:
    root = store.find(cwd, environ)
    if root is None:
        return ["relay entries: not checked, no orchestrator store"], False
    try:
        tracker = tracker or record.Tracker(log.repo_root(cwd))
        entries = _entries(tracker)
    except log.RefusedError as error:
        return [f"relay entries: not checked, {error}"], False
    known = relay_guard.registered(root)
    live = relay_guard.live_orchestrators(root)
    foreign = [
        (name, text.splitlines()[0])
        for name, text in entries
        if not any(line in known for line in text.splitlines()[1:3])
    ]
    lines = [f"relay entries: {len(entries)} approval or decision entries checked"]
    if len(live) > 1:
        lines.append(
            f"relay entries: {len(live)} live sessions are named Orchestrator: {', '.join(live)}"
        )
    lines += [
        f"relay entries: {name}: {first} was not written by the Orchestrator session"
        for name, first in foreign
    ]
    return lines, bool(foreign) or len(live) > 1


SELF_TEST_ORCHESTRATOR = "self-test-orchestrator"
SELF_TEST_WORKER = "self-test-worker"


def _refuses(probe: Callable[[], object]) -> bool:
    try:
        probe()
    except log.RefusedError:
        return True
    return False


def _claim(work: Path) -> object:
    args = argparse.Namespace(
        name=relay_guard.ORCHESTRATOR, now=None, next=None, waiting=None, state=None, session=None
    )
    environ = {relay_guard.HARNESS_ENV: SELF_TEST_WORKER}
    return commands.set_state(args, work, environ, store.utc_now)


def _forged_start(work: Path) -> object:
    event: dict[str, object] = {
        "hook_event_name": "SessionStart",
        "session_title": relay_guard.ORCHESTRATOR,
        "session_id": SELF_TEST_WORKER,
        "cwd": str(work),
    }
    reporter.write_state(event, {}, store.utc_now)
    path = store.session_path(work / ".orchestrator", SELF_TEST_WORKER)
    if relay_guard.reserved(store.read(path).get("name")):
        return "registered"
    raise log.RefusedError("second Orchestrator refused")


def guard_self_test() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        lessons = work / ".orchestrator" / "lessons"
        lessons.mkdir(parents=True)
        (lessons / log.MARKER).write_text("", encoding="utf-8")
        sessions = work / ".orchestrator" / store.SESSIONS
        sessions.mkdir()
        live = {"pid": os.getpid(), "pid_start": store.started(os.getpid())}
        for session, record in (
            (SELF_TEST_ORCHESTRATOR, {"name": relay_guard.ORCHESTRATOR, **live}),
            (SELF_TEST_WORKER, {"name": "worker"}),
        ):
            (sessions / f"{session}.json").write_text(json.dumps(record), encoding="utf-8")
        harness = relay_guard.HARNESS_ENV
        probes: dict[str, Callable[[], object]] = {
            "a wrong id": lambda: relay_guard.check("approve", work, {harness: SELF_TEST_WORKER}),
            "a missing id": lambda: relay_guard.check("approve", work, {}),
            "an ORCH_SESSION_ID spoof": lambda: relay_guard.check(
                "approve", work, {"ORCH_SESSION_ID": SELF_TEST_ORCHESTRATOR}
            ),
            "an orch state set --name Orchestrator claim": lambda: _claim(work),
            "a forged SessionStart payload": lambda: _forged_start(work),
        }
        missed = [label for label, probe in probes.items() if not _refuses(probe)]
        accepted = not _refuses(
            lambda: relay_guard.check("approve", work, {harness: SELF_TEST_ORCHESTRATOR})
        )
    if missed or not accepted:
        why = ", ".join(missed) if missed else "the Orchestrator session itself"
        return False, f"orch approve guard: self-test FAILED on {why}; the deny rule is required"
    return True, (
        f"orch approve guard: self-test refused all {len(probes)} probes and accepted the "
        "Orchestrator session; no deny rule is needed"
    )


def run(cwd: Path, environ: dict[str, str], runner: Runner = run_codex) -> Report:
    repo = log.repo_root(cwd)
    guarded, guard_line = guard_self_test()
    settings_checks = (
        [([guard_line], False)]
        if guarded
        else [
            ([guard_line], False),
            claude_lines(settings_files(repo, environ)),
            codex_lines(repo, environ, runner),
            copilot_lines(repo, environ),
        ]
    )
    checks = [
        *settings_checks,
        rule_parity_lines(environ),
        relay_lines(cwd, environ),
    ]
    unchecked = [] if environ.get("HOME") else ["user settings: not checked, HOME is not set"]
    lessons, stale = lesson_lines(cwd, environ)
    lines = [
        *(line for found, _ in checks for line in found),
        *unchecked,
        wake_adapter_line(environ),
        *lessons,
    ]
    failed = any(refused for _, refused in checks) or stale
    lines.append(f"doctor: {'FAILED' if failed else 'OK'}")
    return Report(lines, failed)
