from __future__ import annotations

import calendar
import hashlib
import importlib.util
import json
import sys
import tempfile
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_migrate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
redact = _load("redact.py", "basicly_tracker_kit_redact")
snapshot = _load("snapshot.py", "basicly_tracker_kit_snapshot")
templates = _load("templates.py", "basicly_tracker_kit_templates")
migrate = _load("migrate.py", "basicly_tracker_kit_migrate")
beans = _load("beans.py", "basicly_tracker_kit_beans")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_view = _load("vault_view.py", "basicly_tracker_kit_vault_view")
vault_share = _load("vault_share.py", "basicly_tracker_kit_vault_share")
canonical = _load("vault_canonical.py", "basicly_tracker_kit_vault_canonical")
private_map = _load("vault_private.py", "basicly_tracker_kit_vault_private")
vault_template = _load("vault_template.py", "basicly_tracker_kit_vault_template")
vault_citations = _load("vault_citations.py", "basicly_tracker_kit_vault_citations")
vault_shapes = vault_clone.vault_shapes

COMMIT_BYTES = vault_share.SEGMENT_BYTES
SESSION = "migrate"
EVERY_PROJECT = vault_view.Want("", all_projects=True)
_UNPUSHED = "nothing was pushed"
_UNWRITTEN = "nothing was written"

Redactor = Callable[[str], str]
Runner = Callable[..., str]


class MigrateError(ValueError):
    pass


@dataclass(frozen=True)
class Import:
    clone: Any
    clock: Callable[[], float]
    redact_holders: bool
    redactor: Redactor | None = None
    private_map: Path | None = None
    overwrite_private_map: bool = False
    runner: Runner = git_runner.run
    code: Path | None = None


@dataclass(frozen=True)
class Prepared:
    result: Any
    writer: str
    lines: list[dict[str, object]]


def _text(lines: Sequence[Mapping[str, object]]) -> bytes:
    return "".join(
        json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n" for line in lines
    ).encode("utf-8")


def ledger_events(ledger: Path | str) -> list:

    found, unreadable = events.read_events(ledger)
    if unreadable:
        first = unreadable[0]
        raise MigrateError(
            f"{len(unreadable)} ledger line(s) do not parse, first {first.path.name}:"
            f"{first.line_number}; run fsck on the ledger and repair it, then migrate again"
        )
    return events.canonical_order(found)


def line_of(event: Any, writer: str, at: float) -> dict[str, object]:

    made = hashlib.sha256(f"{writer} {event.id}".encode()).hexdigest()[:32]
    return {
        "kind": vault_view.LEDGER_KIND,
        "record": event.record,
        vault_view.LEDGER_FIELD: json.loads(events.to_json(event)),
        "id": made,
        "writer": writer,
        "session": SESSION,
        "at": at,
    }


def _prefix_templates(
    found: Sequence[Any], template: Mapping[str, object]
) -> dict[str, dict[str, object]]:
    return {
        event.record.partition("-")[0]: {**template, "prefix": event.record.partition("-")[0]}
        for event in found
    }


def writer_of(found: Sequence[Any], template: Mapping[str, object] | None = None) -> str:
    text = "\n".join(events.to_json(event) for event in found)
    text += json.dumps(_prefix_templates(found, template or {}), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(("canonical-migration-v1\n" + text).encode()).hexdigest()[:32]


def _source_time(text: str) -> float:
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        stamp = datetime.fromisoformat(normalized)
        return calendar.timegm(stamp.utctimetuple()) + stamp.microsecond / 1_000_000
    except ValueError:
        return 0.0
    except OverflowError:
        return 0.0


def lines_of(
    found: Sequence[Any], template: Mapping[str, object] | None = None
) -> tuple[str, list[dict[str, object]]]:
    writer = writer_of(found, template)
    source_templates = _prefix_templates(found, template or {})
    attached: set[str] = set()
    lines = []
    for event in found:
        line = line_of(event, writer, _source_time(event.ts))
        prefix = event.record.partition("-")[0]
        held = source_templates[prefix]
        line[vault_template.IDENTITY] = vault_template.identity(held)
        if prefix not in attached:
            line[vault_template.FIELD] = held
            attached.add(prefix)
        lines.append(line)
    return writer, lines


def digest(found: Sequence[Any], records: Collection[str]) -> str:

    folded = events.fold(found).records
    carried: dict[str, list] = {}
    for event in events.canonical_order(found):
        carried.setdefault(event.record, []).append([event.id, event.kind, dict(event.payload)])
    body = {
        name: [
            snapshot.record_to_dict(folded[name]) if name in folded else None,
            carried.get(name, []),
        ]
        for name in sorted(records)
    }
    text = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def view_events(valid: Sequence[Mapping[str, object]], want: Any) -> list:

    held = {
        name: (*state.holder, state.name)
        for name, state in vault_view.vault_fold.fold(valid).records.items()
        if state.holder is not None
    }
    return vault_view.renumbered(vault_view.carried(valid, want), held)


def _header_bytes(writer: str) -> int:
    return len(_text([{"kind": vault_shapes.SEGMENT_KIND, "writer": writer}]))


def _refuse_a_second_import(clone: Any, found: Sequence[Any]) -> None:

    held = {
        str(line[vault_view.LEDGER_FIELD].get("id"))
        for line in vault_clone.valid_events(clone)
        if line.get("kind") == vault_view.LEDGER_KIND
        and isinstance(line.get(vault_view.LEDGER_FIELD), dict)
    }
    again = [event.id for event in found if event.id in held]
    if again:
        raise MigrateError(
            f"the vault already carries {len(again)} of the {len(found)} canonical events; "
            "this source was migrated before, so nothing was pushed"
        )


def _chunks(plan: Import, head: str, writer: str, lines: list, git: Runner) -> list[str]:

    header = _header_bytes(writer)
    made: list[str] = []
    rest = list(lines)
    while rest:
        _path, old = vault_share._segment(git, head, writer, incoming=len(_text([rest[0]])))
        room = COMMIT_BYTES - (len(old.encode("utf-8")) if old else header)
        take, size = 0, 0
        for line in rest:
            size += len(_text([line]))
            if size > room:
                break
            take += 1
        head = vault_share._build(plan.clone, head, writer, rest[: max(take, 1)], git)
        made.append(head)
        rest = rest[max(take, 1) :]
    return made


def _refuse(name: str, given: tuple, made: tuple, outcome: str) -> None:
    if given[1] != made[1]:
        raise MigrateError(
            f"the {name} differs: {given[0]} {given[1]}, {made[0]} {made[1]}; {outcome}"
        )


def _verified(
    plan: Import, head: str, writer: str, lines: list, source: Sequence[Any]
) -> dict[str, object]:

    def git(args: list[str], **options: Any) -> str:
        return plan.runner(args, plan.clone.bare, **options)

    made = _chunks(plan, head, writer, lines, git) if lines else []
    tip = made[-1] if made else head
    verdicts = vault_shapes.check(plan.clone.bare, tip)
    landed = [
        event
        for verdict in verdicts
        if verdict.valid and verdict.commit in made
        for event in verdict.events
    ]
    _refuse("event count", ("ledger", len(lines)), ("vault", len(landed)), _UNPUSHED)
    records = {event.record for event in source}
    expected = view_events(lines, EVERY_PROJECT)
    actual = view_events(vault_shapes.valid_events(verdicts), EVERY_PROJECT)
    for prefix in {record.partition("-")[0] for record in records}:
        vault_template.carried(vault_shapes.valid_events(verdicts), prefix)
    held = digest(expected, records)
    shown = digest(actual, records)
    _refuse("fold digest", ("ledger", held), ("vault view", shown), _UNPUSHED)
    canonical.check(actual)
    return {"tip": tip, "commits": len(made), "events": len(lines), "digest": shown}


def prepare(
    found: Sequence[Any],
    template: Mapping[str, object],
    redactor: Redactor | None,
    *,
    redact_holders: bool,
) -> Prepared:
    if not found:
        raise MigrateError(
            "source holds no events; run migrate LEDGER --to-vault --preview to check the source"
        )
    public = vault_template.prepare(template, redactor)
    source_template = templates.parse(dict(template or {}), Path(templates.TEMPLATE_FILE))
    public_template = templates.parse(public, Path(templates.TEMPLATE_FILE))
    result = canonical.canonicalize(
        found,
        redactor=redactor,
        redact_holders=redact_holders,
        template=source_template,
        public_template=public_template,
    )
    writer, lines = lines_of(result.events, public)
    largest = max((len(_text([line])) for line in lines), default=0)
    if largest > COMMIT_BYTES - _header_bytes(writer):
        raise MigrateError(
            f"one ledger event or migration template is {largest} bytes, "
            f"above the {COMMIT_BYTES} byte commit limit"
        )
    return Prepared(result, writer, lines)


def to_vault(
    found: Sequence[Any], plan: Import, *, template: Mapping[str, object] | None = None
) -> dict[str, object]:
    prepared = prepare(found, template or {}, plan.redactor, redact_holders=plan.redact_holders)
    result, writer, lines = prepared.result, prepared.writer, prepared.lines
    citations = (
        vault_citations.census(
            plan.code, {row["old"] for row in result.mapping if row["old"] != row["new"]}
        )
        if plan.code is not None
        else {"available": False}
    )
    destination = (
        private_map.prepare(plan.private_map, plan.clone, overwrite=plan.overwrite_private_map)
        if plan.private_map is not None
        else None
    )
    saved = False
    redacted = sum(
        1
        for index, event in enumerate(events.canonical_order(found))
        if lines[index][vault_view.LEDGER_FIELD] != json.loads(events.to_json(event))
    )
    for _attempt in range(vault_share.BULK_ATTEMPTS):
        fetched = vault_clone.fetch(plan.clone, clock=plan.clock, runner=plan.runner)
        _refuse_a_second_import(plan.clone, result.events)
        shown = _verified(plan, str(fetched["head"]), writer, lines, result.events)
        if destination is not None and not saved:
            private_map.write(destination, result.mapping)
            saved = True
        try:
            vault_share._push(
                plan.clone, str(shown["tip"]), plan.runner, git_runner.DEFAULT_TIMEOUT
            )
        except git_runner.GitRunnerError:
            continue
        vault_clone.settle(plan.clone, runner=plan.runner)
        return {
            **shown,
            "redacted": redacted,
            "reminted": result.reminted,
            "touched_fields": list(result.touched),
            "mapping": "saved" if saved else "not-kept",
            "external_citations": citations,
            "not_in_view": len(lines) - len(vault_view.carried(lines, EVERY_PROJECT)),
            "derived_holder_events": len(view_events(lines, EVERY_PROJECT)) - len(lines),
        }
    raise MigrateError(
        f"the vault refused the import push {vault_share.BULK_ATTEMPTS} times; nothing landed, "
        "so run migrate --to-vault again"
    )


def ledger_to_vault(ledger: Path | str, plan: Import) -> dict[str, object]:
    return to_vault(ledger_events(ledger), plan, template=templates.read(ledger))


def backlog_events(source: Any) -> list:
    readers = {**beans.READERS, "br": beans.READERS["beads"]}
    if source.format not in readers:
        raise MigrateError("unknown backlog format; use beads, br or beans")
    read = readers[source.format](source.export, name=source.name)
    with tempfile.TemporaryDirectory() as scratch:
        report = migrate.import_snapshot(scratch, read, actor="migration", clock=lambda: 0.0)
        refused = [*report.rejected, *report.unreadable]
        if refused:
            raise MigrateError(
                f"{len(refused)} {source.format} record(s) were refused, first "
                f"{refused[0].subject}: {refused[0].reason}; the vault took nothing"
            )
        return ledger_events(scratch)


def backlog_to_vault(source: Any, plan: Import) -> dict[str, object]:
    found = backlog_events(source)
    return {**to_vault(found, plan), "records": len({event.record for event in found})}


def from_vault(
    clone: Any,
    prefix: str,
    target: Path,
    *,
    clock: Callable[[], float],
    runner: Runner = git_runner.run,
) -> dict[str, object]:

    try:
        vault_view.ids.validate_prefix(prefix)
    except vault_view.ids.IdError as exc:
        raise MigrateError(f"the prefix cannot name a record: {exc}") from None
    if events.ledger_paths(target):
        raise MigrateError(f"{target} already holds ledger files; name an empty folder")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise MigrateError("export destination is not empty; name an empty folder")
    vault_clone.fetch(clone, clock=clock, runner=runner)
    template = vault_template.carried(vault_clone.valid_events(clone), prefix) or {"prefix": prefix}
    shown = view_events(vault_clone.valid_events(clone), vault_view.Want(prefix))
    canonical.check(shown)
    text = "".join(events.to_json(event) + "\n" for event in shown)
    records = {event.record for event in shown}
    with tempfile.TemporaryDirectory(dir=clone.folder) as scratch:
        (Path(scratch) / events.INITIAL_LOG_NAME).write_text(text, encoding="utf-8")
        back = ledger_events(scratch)
    exported = ("vault view", len(shown)), ("ledger", len(back))
    _refuse("event count", *exported, _UNWRITTEN)
    exported = ("vault view", digest(shown, records)), ("ledger", digest(back, records))
    _refuse("fold digest", *exported, _UNWRITTEN)
    target.mkdir(parents=True, exist_ok=True)
    vault_clone.durable(target / events.INITIAL_LOG_NAME, text)
    if not (target / templates.TEMPLATE_FILE).exists():
        vault_clone.durable(
            target / templates.TEMPLATE_FILE, json.dumps(template, sort_keys=True) + "\n"
        )
    return {"events": len(shown), "records": len(records), "digest": digest(back, records)}
