from __future__ import annotations

import importlib.util
import json
import sys
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


process = _load("process_evidence")
events = process.events
ProcessEvidenceError = process.ProcessEvidenceError


def record_process(
    directory: Path | str,
    record: str,
    evidence: object,
    *,
    completed: bool = False,
    redact: Any = None,
) -> list:
    commands = _load("commands")
    admitted, redact = commands.vault_write.admission(directory, redact, commands.environment())
    ledger = commands._ledger(admitted)
    with events.LedgerLock(ledger) as lock:
        commands._require(ledger, record)
        found = events.read_events(ledger)[0]
        builder = process.confirmation_draft if completed else process.review_draft
        try:
            draft = builder(
                found,
                record,
                evidence,
                commands.writers.writer_class(commands.environment()),
                template=commands.templates.load(ledger),
            )
        except ProcessEvidenceError as error:
            raise error.at(Path(directory)) from None
        if isinstance(redact, commands.vault_write.WriteContext) and redact.target is not None:
            saved = json.loads(draft.payload["value"])
            process._safe_commands(saved["checks"], commands.vault_write.effective_redactor(redact))
        return commands._append(ledger, [draft], redact, lock)
