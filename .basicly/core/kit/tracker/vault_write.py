from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_write.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")
templates = _load("templates.py", "basicly_tracker_kit_templates")
parent_progress = _load("parent_progress.py", "basicly_tracker_kit_parent_progress")
values = _load("values.py", "basicly_tracker_kit_values")
holders = _load("holders.py", "basicly_tracker_kit_holders")
review = _load("review.py", "basicly_tracker_kit_review")
writers = _load("writers.py", "basicly_tracker_kit_writers")
recurrence = _load("recurrence.py", "basicly_tracker_kit_recurrence")
redact = _load("redact.py", "basicly_tracker_kit_redact")
git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
vault_config = _load("vault_config.py", "basicly_tracker_kit_vault_config")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_hooks = _load("vault_hooks.py", "basicly_tracker_kit_vault_hooks")
vault_claim = _load("vault_claim.py", "basicly_tracker_kit_vault_claim")
vault_view = _load("vault_view.py", "basicly_tracker_kit_vault_view")
vault_pending = _load("vault_pending.py", "basicly_tracker_kit_vault_pending")

LEDGER_KIND = "ledger"
LEDGER_FIELD = "ledger"
vault_session = _load("vault_session.py", "basicly_tracker_kit_vault_session")
SESSION = vault_session.SESSION
session_of = vault_session.session_of
given_session = vault_session.given_session
IMMEDIATE = ("CI", "BASICLY_TRACKER_EPHEMERAL")
_UNREACHED = (vault_clone.CloneError, git_runner.GitRunnerError, events.LockUnavailableError)

Clock = Callable[[], float]
Redactor = Callable[[str], str]


class NoClockError(events.LedgerError):
    pass


@dataclass(frozen=True)
class WriteContext:
    redactor: Redactor | None
    clock: Clock
    target: Target | None = None
    source: Path | None = None
    queued: dict[str, object] | None = None


def parts(given: WriteContext | Redactor | None) -> tuple[Redactor | None, Clock | None]:
    if isinstance(given, WriteContext):
        return given.redactor, given.clock
    return given, None


class VaultUnreadError(events.LedgerError):
    pass


class VaultRefusedError(events.LedgerError):
    def __init__(self, report: Mapping[str, object]) -> None:
        super().__init__(json.dumps(dict(report), sort_keys=True, ensure_ascii=False))
        self.report = dict(report)


@dataclass(frozen=True)
class Queued:
    record: str
    id: str


@dataclass(frozen=True)
class Target:
    clone: Any
    state: Path
    session: str
    immediate: bool
    clock: Clock
    prefix: str = ""

    def origin(self) -> Any:
        return vault_queue.Origin(self.session, self.immediate, self.clock)


def config_of(ledger: Path | str) -> Any:
    return vault_config.load(Path(ledger).resolve())


def target_of(ledger: Path | str, environ: Mapping[str, str], clock: Clock | None) -> Target | None:

    config = config_of(ledger)
    if config is None:
        return None
    if clock is None:
        raise NoClockError(
            f"{config.path} names a vault, and a vault write needs the clock of the write "
            "context that cli.py builds; run the write through cli.py"
        )
    state = vault_clone.state_root(environ, Path.home(), windows=os.name == "nt")
    return Target(
        vault_clone.locate(state, config.vault),
        state,
        session_of(environ),
        any(environ.get(name) for name in IMMEDIATE),
        clock,
        config.prefix,
    )


def prefix(ledger: Path | str, given: str) -> str:
    config = config_of(ledger)
    return given if config is None else config.prefix


def _redactor(given: Redactor | None) -> Redactor:
    return redact.text if given is None else lambda value: redact.text(given(value))


def effective_redactor(given: WriteContext | Redactor | None) -> Redactor | None:
    redactor, _clock = parts(given)
    if isinstance(given, WriteContext) and given.target is not None:
        return _redactor(redactor)
    return redactor


def _refused(ledger: Path, drafts: Sequence[Any], actor: str) -> Sequence[Any]:

    template = templates.load(ledger)
    found = events.read_events(ledger)[0]
    states = events.fold(found).records
    drafts, progress_parents = parent_progress.progress(found, drafts)
    values.refuse(events, drafts, template, states, found)
    holders.refuse(states, drafts)
    review_drafts = [
        draft
        for draft in drafts
        if not (
            draft.record in progress_parents
            and draft.kind == events.KIND_STATUS
            and draft.payload.get("status") == "in_progress"
        )
    ]
    try:
        review.refuse(states, review_drafts, actor, template, found=found)
    except review.UnreviewedError as error:
        raise error.at(ledger) from None
    return drafts


def view_of(target: Target, ledger: Path) -> Path:

    if not target.prefix:
        raise VaultUnreadError(
            "the vault write names no project prefix, so it cannot read its records from the "
            "vault view; build the target with target_of, which reads .basicly-tracker.toml"
        )
    template = ledger if ledger.is_dir() else None
    want = vault_view.Want(target.prefix, False, template)
    try:
        return vault_pending.present(target.clone, want, clock=target.clock)
    except vault_view.ViewError as exc:
        raise VaultUnreadError(
            f"{exc}; the write needs the vault view to mint its seq and id, so nothing is queued"
        ) from None


def born_records(target: Target) -> set[str]:
    found = vault_clone.valid_events(target.clone)
    found += vault_queue.pending(target.clone.folder / vault_queue.QUEUE_NAME)
    carried = vault_view.carried(found, vault_view.Want(target.prefix))
    return {event.record for event in carried if event.kind == events.KIND_CREATED}


def admission(
    directory: Path | str, given: WriteContext | Redactor | None, environ: Mapping[str, str]
) -> tuple[Path, WriteContext | Redactor | None]:
    ledger = Path(directory)
    config = vault_config.load(ledger)
    if config is not None:
        frozen = _load("ledger_freeze.py", "basicly_tracker_kit_ledger_freeze")
        frozen.check(config.path.parent / frozen.LEDGER)
    _redactor, clock = parts(given)
    if isinstance(given, WriteContext) and given.target is not None:
        return view_of(given.target, given.source or ledger), given
    target = target_of(ledger, environ, clock)
    if target is None:
        return ledger, given
    if not isinstance(given, WriteContext):
        raise NoClockError("vault admission needs the CLI write context")
    return view_of(target, ledger), replace(given, target=target, source=ledger)


def _vault_refused(target: Target, ledger: Path, drafts: Sequence[Any]) -> None:
    states = events.fold(events.read_events(ledger)[0]).records
    created = {draft.record for draft in drafts if draft.kind == events.KIND_CREATED}
    available = {record for record, state in states.items() if not state.tombstoned} | created
    for draft in drafts:
        if draft.record not in available:
            raise events.LedgerError(
                f"the vault holds no record {draft.record}; nothing was written"
            )
        if _names_the_holder(draft) or (
            draft.kind == events.KIND_CREATED and events.HOLDER_FIELD in draft.payload
        ):
            raise events.LedgerError(
                f"{draft.record} cannot set {events.HOLDER_FIELD} as a ledger field in vault "
                f"mode; nothing was written, run `claim {draft.record}` "
                f"or `unassign {draft.record}`"
            )
        if draft.kind == events.KIND_EDGE:
            other = str(draft.payload.get("to", ""))
            if other not in available:
                raise events.LedgerError(f"the vault holds no record {other}; nothing was written")
            if draft.record not in created:
                edges = _load("edges.py", "basicly_tracker_kit_edges")
                edge_type = str(draft.payload.get("type", ""))
                edges.refuse_edge(ledger, draft.record, other, edge_type)
                edges.refuse_cycle(ledger, draft.record, other, edge_type)
        if draft.kind == events.KIND_EDGE_RETRACTED:
            edges = _load("edges.py", "basicly_tracker_kit_edges")
            edges.refuse_retraction(
                edges.queries.views_and_children(ledger)[0],
                draft.record,
                str(draft.payload.get("to", "")),
                str(draft.payload.get("type", "")),
            )
        if draft.kind == events.KIND_STATUS and draft.payload.get("status") == "in_progress":
            held = vault_claim.holder(target.clone, draft.record)
            mine = (vault_queue.writer_of(target.state), target.session)
            if held != mine:
                raise events.LedgerError(
                    f"{draft.record} needs this session's canonical vault claim before it can "
                    f"start; nothing was written, run `claim {draft.record}`"
                )


def _names_the_holder(event: Any) -> bool:
    return event.kind == events.KIND_FIELD and event.payload.get("name") == events.HOLDER_FIELD


def _seed(view: Path, records: set[str]) -> list[str]:

    shown = [
        event
        for event in events.read_events(view)[0]
        if not (event.actor == vault_view.HOLDER_ACTOR and _names_the_holder(event))
    ]
    found = [event for event in shown if event.record in records]
    found += [event for event in shown if events.WITHDRAWN_FROM in event.payload]
    lines = {event.id: events.to_json(event) for event in found}
    return list(lines.values())


def _minted(
    target: Target, view: Path, drafts: Sequence[Any], *, repeat: bool, **options: Any
) -> list:

    seed = _seed(view, {draft.record for draft in drafts})
    vault_clone.private(target.clone.folder)
    with tempfile.TemporaryDirectory(dir=target.clone.folder) as scratch:
        folder = Path(scratch)
        if seed:
            events.append_lines(folder / events.INITIAL_LOG_NAME, seed)
        resolved = recurrence.at_the_generation_this_write_needs(
            events, folder, drafts, repeat=repeat, redact=options["redact"]
        )
        return events.append(folder, resolved, **options)


def line_of(event: Any) -> dict[str, object]:
    carried = json.loads(events.to_json(event))
    return {"kind": LEDGER_KIND, "record": event.record, LEDGER_FIELD: carried}


@dataclass(frozen=True)
class Write:
    ledger: Path
    given: WriteContext | Redactor | None
    lock: Any
    environ: Mapping[str, str]


def land(write: Write, drafts: Sequence[Any], *, repeat: bool = False) -> list:

    ledger, given = write.ledger, write.given
    if not isinstance(given, WriteContext) or given.target is None:
        ledger, given = admission(ledger, given, write.environ)
    actor = writers.writer_class(write.environ)
    target = given.target if isinstance(given, WriteContext) else None
    if target is not None:
        _vault_refused(target, ledger, drafts)
    drafts = _refused(ledger, drafts, actor)
    _redactor_given, clock = parts(given)
    redactor = effective_redactor(given)
    if target is None:
        resolved = recurrence.at_the_generation_this_write_needs(
            events, ledger, drafts, repeat=repeat, redact=redactor
        )
        return events.append(
            ledger, resolved, actor=actor, redact=redactor, held_lock=write.lock, clock=clock
        )
    clock = target.clock
    minted = _minted(
        target,
        ledger,
        drafts,
        repeat=repeat,
        actor=actor,
        redact=redactor,
        clock=clock,
    )
    if minted:
        lines = [line_of(event) for event in minted]
        queued = vault_queue.write(target.clone, lines, state=target.state, origin=target.origin())
        shared = vault_hooks.due_share(target.clone, target.state, clock, now=target.immediate)
        if isinstance(given, WriteContext) and given.queued is not None:
            given.queued.update({**queued, "shared": shared})
    return minted


def _answered(shown: Mapping[str, object], key: str) -> list:
    if shown.get("exit") != vault_claim.LANDED:
        raise VaultRefusedError(shown)
    return [Queued(str(shown.get("record")), str(shown.get(key)))]


def claim(
    ledger: Path,
    record: str,
    environ: Mapping[str, str],
    given: WriteContext | Redactor | None,
    *,
    take: bool = False,
) -> list | None:

    target = target_of(ledger, environ, parts(given)[1])
    if target is None:
        return None
    if take:
        return _answered(
            {
                "exit": vault_claim.FIX,
                "record": record,
                "fix": f"a vault claim never takes; run unassign {record} --take, then claim it",
            },
            "claim",
        )
    name = holders.chosen_holder(ledger, environ)
    ask = vault_claim.Ask(
        target.clone, target.state, record, target.session, target.clock, name=name
    )
    return _answered(vault_claim.claim(ask), "claim")


def _fetched(clone: Any, clock: Clock) -> bool:
    try:
        shown = vault_clone.fetch(clone, clock=clock, timeout=vault_claim.PROBE)
    except _UNREACHED:
        return False
    return bool(shown.get("fetched"))


def release(target: Target, record: str, *, take: bool) -> dict[str, object]:

    if not target.session:
        return {"exit": vault_claim.FIX, "fix": vault_claim.NAME_SESSION}
    clone = target.clone
    if not _fetched(clone, target.clock):
        return {
            "exit": vault_claim.UNREACHABLE,
            "record": record,
            "check": f"git fetch {clone.url} refs/heads/main",
        }
    mine = (vault_queue.writer_of(target.state), target.session)
    held = vault_claim.holder(clone, record)
    if held is None:
        return {"exit": vault_claim.FIX, "record": record, "fix": f"{record} has no holder"}
    if held != mine and not take:
        return {
            "exit": vault_claim.LOST,
            "record": record,
            "holder": {"writer": held[0], "session": held[1]},
            "next": f"unassign {record} --take",
        }
    kinds = (vault_claim.vault_fold.TAKE,) if held != mine else ()
    drafts = [
        {"kind": kind, "record": record} for kind in (*kinds, vault_claim.vault_fold.UNASSIGN)
    ]
    queued = vault_queue.write(clone, drafts, state=target.state, origin=target.origin())
    shared = vault_hooks.due_share(clone, target.state, target.clock, now=target.immediate)
    made = queued["events"]
    return {"exit": vault_claim.LANDED, "record": record, "unassign": made[-1], "shared": shared}


def unassign(
    ledger: Path,
    record: str,
    environ: Mapping[str, str],
    given: WriteContext | Redactor | None,
    *,
    take: bool = False,
) -> list | None:

    target = target_of(ledger, environ, parts(given)[1])
    if target is None:
        return None
    return _answered(release(target, record, take=take), "unassign")
