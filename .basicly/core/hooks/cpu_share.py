from __future__ import annotations

import os
from collections.abc import Sequence

AUTO = "auto"

WORKERS = "{workers}"

CORES_PER_JOB = 8


def cores() -> int:
    return os.process_cpu_count() or 1


def resolve_jobs(value: object, available: int | None = None) -> int:
    if value == AUTO:
        return max(1, (available or cores()) // CORES_PER_JOB)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f'verify.jobs must be a whole number of at least 1 or "{AUTO}"')
    return value


def workers(jobs: int, available: int | None = None) -> int:
    return max(1, (available or cores()) // max(1, jobs))


def expand(command: Sequence[str], jobs: int, available: int | None = None) -> list[str]:
    share = str(workers(jobs, available))
    return [share if part == WORKERS else part for part in command]
