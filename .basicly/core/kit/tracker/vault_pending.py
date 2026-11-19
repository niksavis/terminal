from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's " + name + ".py is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


vault_view = _load("vault_view")
vault_queue = _load("vault_queue")
events = vault_view.events
KEY_NAME = "pending.key"
PENDING_NAME = "pending-records.json"
LEGACY_RECORD = "basicly-pvdo68d"


def projection(published: Any, pending: Any, want: Any) -> tuple:
    legacy = {
        str(line.get("id") or f"unidentified-{index}")
        for index, line in enumerate([*published, *pending])
        if line.get("kind") == "comment"
        and (
            want.all_projects
            or not isinstance(line.get("record"), str)
            or not vault_view.ids.is_record_id(str(line["record"]))
            or str(line["record"]).partition("-")[0] == want.prefix
        )
    }
    if legacy:
        raise vault_view.ViewError(
            f"{len(legacy)} legacy vault comments are not shown; "
            f"see {LEGACY_RECORD} for legacy projection"
        )
    carried = vault_view.carried(published, want)
    published_ids = {event.id for event in carried}
    published_wrappers = {str(line.get("id", "")) for line in published}
    waiting = vault_view.carried(pending, want)
    unshared = {event.record for event in waiting if event.id not in published_ids}
    unshared.update(
        str(line["record"])
        for line in pending
        if line.get("kind") != vault_view.LEDGER_KIND
        and str(line.get("id", "")) not in published_wrappers
        and isinstance(line.get("record"), str)
        and vault_view.ids.is_record_id(str(line["record"]))
        and (want.all_projects or str(line["record"]).partition("-")[0] == want.prefix)
    )
    combined = [
        *published,
        *(line for line in pending if line.get("kind") == vault_view.LEDGER_KIND),
    ]
    held = {
        record: (*state.holder, state.name)
        for record, state in vault_view.vault_fold.fold(combined).records.items()
        if state.holder is not None
    }
    return combined, held, unshared


def present(clone: Any, want: Any, *, clock: Callable[[], float]) -> Path:
    base = vault_view.present(clone, want, clock=clock)
    published = vault_view.vault_clone.valid_events(clone)
    pending = vault_queue.pending(clone.folder / vault_queue.QUEUE_NAME)
    combined, held, unshared = projection(published, pending, want)
    template = vault_view.templates.read(base)
    payload = json.dumps([published, pending, template], sort_keys=True, ensure_ascii=False)
    key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    folder = clone.folder / ("pending.all" if want.all_projects else "pending-" + want.prefix)
    vault_view.vault_clone.private(folder)
    with events.LedgerLock(folder):
        marker = folder / KEY_NAME
        if marker.is_file() and marker.read_text(encoding="utf-8") == key:
            return folder
        shown = vault_view.renumbered(vault_view.carried(combined, want), held)
        lines = "".join(events.to_json(event) + "\n" for event in shown)
        vault_view.snapshot.snapshot_path(folder).unlink(missing_ok=True)
        vault_view.vault_clone.durable(folder / events.INITIAL_LOG_NAME, lines)
        vault_view.vault_clone.durable(
            folder / vault_view.templates.TEMPLATE_FILE, json.dumps(template, sort_keys=True) + "\n"
        )
        vault_view.vault_clone.durable(folder / PENDING_NAME, json.dumps(sorted(unshared)) + "\n")
        vault_view.vault_clone.durable(marker, key)
    return folder


def records(directory: Path | str) -> set[str]:
    marker = Path(directory) / PENDING_NAME
    if not marker.is_file():
        return set()
    try:
        found = json.loads(marker.read_text(encoding="utf-8"))
    except OSError:
        raise vault_view.ViewError(
            "pending view metadata is unreadable; run status and retry"
        ) from None
    except ValueError:
        raise vault_view.ViewError(
            "pending view metadata is unreadable; run status and retry"
        ) from None
    if not isinstance(found, list) or not all(
        isinstance(record, str) and vault_view.ids.is_record_id(record) for record in found
    ):
        raise vault_view.ViewError("pending view metadata is invalid; run status and retry")
    return set(found)


def annotate(directory: Path | str, report: Any) -> Any:
    waiting = records(directory)

    def marked(value: Any) -> Any:
        if isinstance(value, list):
            return [marked(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: marked(item) for key, item in value.items()}
        record = value.get("record", value.get("id"))
        if (isinstance(record, str) and record in waiting) or (waiting and "by_status" in value):
            result["sharing"] = "pending"
        return result

    return marked(report)
