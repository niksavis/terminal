from __future__ import annotations

from pathlib import Path

LOG_GLOB = "events-*.jsonl"
PENDING_GLOB = "pending-*.jsonl"
INITIAL_LOG_NAME = "events-0001.jsonl"


def log_paths(directory: Path | str) -> list[Path]:
    return sorted(Path(directory).glob(LOG_GLOB))


def pending_paths(directory: Path | str) -> list[Path]:
    return sorted(Path(directory).glob(PENDING_GLOB))


def ledger_paths(directory: Path | str) -> list[Path]:
    return log_paths(directory) + pending_paths(directory)
