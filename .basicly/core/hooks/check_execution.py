from __future__ import annotations

import subprocess  # nosec B404
import sys
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path
from typing import NamedTuple

Resolve = Callable[[list[str], Path], list[str]]


class Plan(NamedTuple):
    checks: list[tuple[str, list[str]]]
    skips: dict[str, str]
    fail_fast: bool
    jobs: int
    exclusive: frozenset[str] = frozenset()


def run(repo_root: Path, plan: Plan, resolve: Resolve) -> tuple[list[dict], list[str]]:
    if plan.jobs > 1:
        return _run_parallel(repo_root, plan, resolve)
    return _run_serial(repo_root, plan, resolve)


def _execute(
    name: str, command: list[str], repo_root: Path, resolve: Resolve, *, capture: bool
) -> dict:
    start = time.perf_counter()
    output = ""
    try:
        result = subprocess.run(  # nosec B603
            resolve(command, repo_root),
            cwd=repo_root,
            check=False,
            capture_output=capture,
            text=capture,
            encoding="utf-8" if capture else None,
            errors="replace" if capture else None,
        )
        code = result.returncode
        if capture:
            output = (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        output = (
            f"FAILED: {name} — command not found: {command[0]} "
            f"(install it or edit [[verify.checks]] in basicly.toml)\n"
        )
        code = 127
    except OSError as exc:
        output = f"FAILED: {name} — cannot run {command[0]} ({exc.strerror or exc})\n"
        code = 126
    if not capture and output:
        print(output, end="", file=sys.stderr)
        output = ""
    return {
        "name": name,
        "disposition": "executed",
        "returncode": code,
        "duration_s": time.perf_counter() - start,
        "output": output,
    }


def _finish(outcome: dict, failed: list[str]) -> dict:
    if outcome["returncode"] != 0:
        failed.append(outcome["name"])
        print(f"FAILED: {outcome['name']} ({outcome['duration_s']:.2f}s)", file=sys.stderr)
    return {key: value for key, value in outcome.items() if key != "output"}


def _skipped(name: str, reason: str) -> dict:
    print(f"==> {name} SKIPPED: {reason}", flush=True)
    return {"name": name, "disposition": "not-selected", "reason": reason}


def _run_serial(repo_root: Path, plan: Plan, resolve: Resolve) -> tuple[list[dict], list[str]]:
    checks, skips, fail_fast = plan.checks, plan.skips, plan.fail_fast
    failed: list[str] = []
    outcomes: list[dict] = []
    for name, command in checks:
        if name in skips:
            outcomes.append(_skipped(name, skips[name]))
            continue
        if fail_fast and failed:
            outcomes.append(_blocked_outcome(name, failed[0]))
            continue
        print(f"==> {name}", flush=True)
        outcomes.append(_finish(_execute(name, command, repo_root, resolve, capture=False), failed))
    return outcomes, failed


def _run_parallel(repo_root: Path, plan: Plan, resolve: Resolve) -> tuple[list[dict], list[str]]:
    checks, skips, fail_fast = plan.checks, plan.skips, plan.fail_fast
    stop = threading.Event()
    stopped_by: list[str] = []

    def task(name: str, command: list[str]) -> dict | None:
        if stop.is_set():
            return None
        outcome = _execute(name, command, repo_root, resolve, capture=True)
        if fail_fast and outcome["returncode"] != 0:
            stopped_by.append(name)
            stop.set()
        return outcome

    failed: list[str] = []
    outcomes: list[dict] = []
    with ThreadPoolExecutor(max_workers=plan.jobs) as pool:
        futures = {}
        for name, command in checks:
            if name in skips:
                continue
            if name in plan.exclusive:
                wait(futures.values())
            futures[name] = pool.submit(task, name, command)
            if name in plan.exclusive:
                wait([futures[name]])
        for name, _ in checks:
            if name in skips:
                outcomes.append(_skipped(name, skips[name]))
                continue
            outcome = futures[name].result()
            if outcome is None:
                outcomes.append(_blocked_outcome(name, stopped_by[0]))
                continue
            print(f"==> {name}", flush=True)
            print(outcome["output"], end="", flush=True)
            outcomes.append(_finish(outcome, failed))
    return outcomes, failed


def _blocked_outcome(name: str, failed: str) -> dict:
    reason = f"not run after failed check {failed}"
    print(f"==> {name} NOT RUN: {reason}", flush=True)
    return {"name": name, "disposition": "not-run", "reason": reason}
