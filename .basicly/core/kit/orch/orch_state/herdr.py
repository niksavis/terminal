from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path

import runner

SOURCE = "basicly-orch"
LABEL_MAX = 80
TIMEOUT_SECONDS = 1.0
PANE_ID = re.compile(r"[A-Za-z0-9]{1,16}:[A-Za-z0-9]{1,32}")


def clean(text: str) -> str:
    kept = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in text)
    return " ".join(kept.split())[:LABEL_MAX]


def pane_id(environ: dict[str, str]) -> str | None:
    value = environ.get("HERDR_PANE_ID", "")
    return value if PANE_ID.fullmatch(value) else None


def binary(environ: dict[str, str]) -> str | None:
    named = environ.get("HERDR_BIN_PATH", "")
    if named and Path(named).is_absolute() and os.access(named, os.X_OK):
        return named
    return runner.which("herdr", environ.get("PATH"))


def argv(
    herdr: str,
    pane: str,
    labels: dict[str, str] | None,
    ttl_ms: int | None,
    seq: int | None = None,
) -> list[str]:
    command = [herdr, "pane", "report-metadata", pane, "--source", SOURCE]
    if labels:
        for status, text in labels.items():
            command += ["--state-label", f"{status}={clean(text)}"]
        if ttl_ms is not None:
            command += ["--ttl-ms", str(ttl_ms)]
    else:
        command.append("--clear-state-labels")
    command += ["--seq", str(seq if seq is not None else time.time_ns())]
    return command


def report(command: list[str], environ: dict[str, str]) -> None:
    runner.quiet(command, environ, TIMEOUT_SECONDS)
