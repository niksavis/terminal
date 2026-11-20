from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

import runner
from orch_lessons.log import RefusedError

RECORD_PREFIX = "orchestration-record:"
LEDGER = Path(".basicly/ledger")
TRACKER_CLI = Path(".basicly/core/kit/tracker/cli.py")
ACTIVE = ("open", "in_progress")

Runner = Callable[[list[str]], str]


def run_tracker(argv: list[str]) -> str:
    done = runner.capture(argv, 60)
    if done.code != 0:
        raise RefusedError(f"the tracker refused: {done.err.strip() or done.out.strip()}")
    return done.out


class Tracker:
    def __init__(self, repo: Path, runner: Runner = run_tracker) -> None:
        cli = repo / TRACKER_CLI
        if not cli.is_file():
            raise RefusedError(
                f"{TRACKER_CLI} is missing in {repo}; install the basicly tracker kit first"
            )
        self.base = [sys.executable, str(cli)]
        self.ledger = str(repo / LEDGER)
        self.runner = runner

    def active_records(self) -> list[dict[str, object]]:
        argv = [*self.base, "list", self.ledger, "--summary"]
        for status in ACTIVE:
            argv += ["--status", status]
        records = json.loads(self.runner(argv)).get("records", [])
        return [record for record in records if isinstance(record, dict)]

    def matching(self, query: str) -> list[str]:
        argv = [*self.base, "list", self.ledger, "--query", query, "--summary"]
        records = json.loads(self.runner(argv)).get("records", [])
        return [str(item.get("record")) for item in records if isinstance(item, dict)]

    def comments(self, record: str) -> list[str]:
        shown = json.loads(self.runner([*self.base, "show", self.ledger, record]))
        found = shown.get("comments", []) if isinstance(shown, dict) else []
        return [text for text in found if isinstance(text, str)]

    def comment(self, record: str, text: str) -> None:
        self.runner([*self.base, "comment", self.ledger, record, text])


def _title(record: dict[str, object]) -> str:
    fields = record.get("fields")
    title = fields.get("title") if isinstance(fields, dict) else None
    return title if isinstance(title, str) else ""


def find(tracker: Tracker) -> str:
    matches = [
        str(record.get("record"))
        for record in tracker.active_records()
        if _title(record).startswith(RECORD_PREFIX)
    ]
    if len(matches) != 1:
        listed = f": {', '.join(matches)}" if matches else ""
        raise RefusedError(
            f"found {len(matches)} active records whose title starts with "
            f"{RECORD_PREFIX!r}{listed}; exactly one must match"
        )
    return matches[0]
