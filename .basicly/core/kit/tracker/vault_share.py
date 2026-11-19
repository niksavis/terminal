from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_share.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")

SEGMENT_BYTES = 1 << 20
BULK_ATTEMPTS = 5
BATCH_QUIET = 0.1
SHARE_LOCK = "share"
SHARED_AT = "shared.at"
PROGRESS_NAME = "share.progress"
SIGNED_ONLY = (
    "the vault refused unsigned commits; share commits are unsigned and authored by the writer "
    "id, so turn off required commit signatures for the vault repository"
)

Runner = Callable[..., str]


class ShareError(ValueError):
    pass


class DeadlineError(ShareError):
    pass


@dataclass(frozen=True)
class Plan:
    wall: Callable[[], float]
    urgent: bool = False
    deadline_s: float = 10.0
    attempts: int = BULK_ATTEMPTS
    lock_wait: float | None = None
    fresh: bool = False
    keep_going: bool = True
    unlocked: bool = False
    stop_when: Callable[[], bool] | None = None


def _text(lines: Sequence[Mapping[str, object]]) -> str:
    return "".join(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n" for line in lines)


def prune(clone: Any) -> list[dict[str, object]]:

    queue = clone.folder / vault_queue.QUEUE_NAME
    valid = vault_clone.valid_ids(clone)
    with events.LedgerLock(clone.folder):
        lines = vault_queue.pending(queue)
        keep = [line for line in lines if str(line.get("id")) not in valid]
        if len(keep) != len(lines):
            vault_clone.durable(queue, _text(keep))
    return keep


def _segment(git: Runner, head: str, writer: str, *, incoming: int = 0) -> tuple:

    folder = f"{vault_clone.vault_shapes.LOG_ROOT}/{writer}/"
    listed = git(["ls-tree", "--name-only", head, folder]).split()
    if not listed:
        return f"{folder}00001.jsonl", ""
    if any(not Path(path).stem.isdecimal() or Path(path).suffix != ".jsonl" for path in listed):
        raise ShareError("a segment filename is not numeric JSONL; run vault-check before sharing")
    path = max(listed, key=lambda path: int(Path(path).stem))
    old = git(["cat-file", "blob", f"{head}:{path}"])
    if len(old.encode("utf-8")) + incoming <= SEGMENT_BYTES:
        return path, old
    return f"{folder}{int(Path(path).stem) + 1:05d}.jsonl", ""


def _segments(git: Runner, head: str, writer: str, batch: list) -> dict[str, bytes]:
    header = _text([{"kind": vault_clone.vault_shapes.SEGMENT_KIND, "writer": writer}]).encode(
        "utf-8"
    )
    lines = [_text([line]).encode("utf-8") for line in batch]
    if not lines:
        raise ShareError("an empty batch cannot create a segment")
    for line in lines:
        if len(header) + len(line) > SEGMENT_BYTES:
            raise ShareError(
                f"one event is {len(line)} bytes, above the segment limit of "
                f"{SEGMENT_BYTES - len(header)} bytes; nothing was pushed"
            )
    path, old = _segment(git, head, writer, incoming=len(lines[0]))
    content = bytearray(old.encode("utf-8") if old else header)
    packed: dict[str, bytes] = {}
    for line in lines:
        if len(content) + len(line) > SEGMENT_BYTES:
            packed[path] = bytes(content)
            held = Path(path)
            path = (held.parent / f"{int(held.stem) + 1:05d}.jsonl").as_posix()
            content = bytearray(header)
        content.extend(line)
    packed[path] = bytes(content)
    return packed


def _build(clone: Any, head: str, writer: str, batch: list, git: Runner) -> str:

    packed = _segments(git, head, writer, batch)
    token = uuid.uuid4().hex
    blob_file = clone.folder / f"share-{token}.blob"
    index = clone.folder / f"share-{token}.index"
    env = {"GIT_INDEX_FILE": str(index)}
    try:
        git(["read-tree", head], env=env)
        for path, content in packed.items():
            blob_file.write_bytes(content)
            hashed = ["hash-object", "-w", "--no-filters", str(blob_file)]
            blob = git(hashed).strip()
            entry = ["update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"]
            git(entry, env=env)
        tree = git(["write-tree"], env=env).strip()
    finally:
        for leftover in (blob_file, index, index.with_name(index.name + ".lock")):
            leftover.unlink(missing_ok=True)
    who = {"NAME": writer[:12], "EMAIL": f"{writer}@writers.basicly.invalid"}
    ident = {
        f"GIT_{role}_{key}": value for role in ("AUTHOR", "COMMITTER") for key, value in who.items()
    }
    made = [
        "-c",
        "commit.gpgSign=false",
        "commit-tree",
        tree,
        "-p",
        head,
        "-m",
        f"batch {len(batch)}",
    ]
    return git(made, env=ident).strip()


@dataclass
class _BatchBuilder:
    clone: Any
    writer: str
    prepared: tuple[str, list, str] | None = None
    urgent: bool = False

    def build(self, head: str, batch: list, git: Runner) -> str:
        previous = self.prepared
        if previous is None or previous[0] != head or previous[1] != batch:
            previous = (head, batch, _build(self.clone, head, self.writer, batch, git))
            self.prepared = previous
        return previous[2]

    def latest(
        self, head: str, batch: list, git: Runner, budget: Callable[[], float]
    ) -> tuple[str, list]:
        settling = self.urgent and self.prepared is None
        while True:
            budget()
            commit = self.build(head, batch, git)
            arrived = [line for line in prune(self.clone) if line.get("writer") == self.writer]
            if not arrived:
                return commit, arrived
            if arrived == batch:
                if settling:
                    settling = False
                    time.sleep(min(BATCH_QUIET, budget()))
                    continue
                return commit, arrived
            batch = arrived
            if not self.urgent:
                return self.build(head, batch, git), batch


def _push(clone: Any, commit: str, runner: Runner, timeout: float) -> None:
    vault_clone.protect(clone)
    hooks = clone.bare / "hooks"
    pushed = [
        "-c",
        f"core.hooksPath={hooks}",
        "push",
        "--quiet",
        "origin",
        f"{commit}:refs/heads/main",
    ]
    runner(pushed, clone.bare, timeout=timeout, allow_file=clone.allow_file)


def _budget(plan: Plan, started: float, clock: Callable[[], float]) -> float:
    if not plan.urgent:
        return git_runner.DEFAULT_TIMEOUT
    left = plan.deadline_s - (clock() - started)
    if left <= 0:
        raise DeadlineError(
            f"the urgent share passed its {plan.deadline_s:g} s deadline; run sync again"
        )
    return left


def _again(plan: Plan, attempt: int, started: float, clock: Callable[[], float]) -> bool:
    if plan.urgent:
        return clock() - started < plan.deadline_s
    return attempt < plan.attempts


def _stopped(head: str, stop: Mapping[str, object], clone: Any) -> dict[str, object]:
    payload = stop.get("payload")
    said = payload if isinstance(payload, Mapping) else {}
    return {
        "shared": 0,
        "head": head,
        "pending": len(vault_queue.pending(clone.folder / vault_queue.QUEUE_NAME)),
        "ended": {"reason": said.get("reason"), "successor": said.get("successor")},
    }


def _retry_head(clone: Any, plan: Plan, runner: Runner, budget: float, previous: str) -> dict:
    if plan.urgent and previous:
        generation = vault_clone._read(clone.folder / vault_clone.FETCH_GENERATION_NAME)
        head = vault_clone._advanced_head(clone, previous, runner, budget)
        if head:
            return {"head": head, "seen": head, "moved": False}
        return vault_clone.fetch_with(
            clone,
            vault_clone.Fetch(
                plan.wall, runner, budget, budget, coalesce=True, previous_generation=generation
            ),
        )
    return {}


def _share_head(clone: Any, plan: Plan, runner: Runner, budget: float, *, fresh: bool) -> dict:
    if fresh:
        settled = vault_clone.settle(clone, runner=runner, timeout=budget, lock_wait=budget)
        return {**settled, "head": settled["seen"]}
    if plan.urgent:
        return vault_clone.fetch_with(
            clone, vault_clone.Fetch(plan.wall, runner, budget, budget, coalesce=True)
        )
    return vault_clone.fetch(
        clone, clock=plan.wall, runner=runner, timeout=budget, lock_wait=budget
    )


def _pending_share(clone: Any, head: str, total: int, waited: float, fetch_waits: float) -> dict:
    return {
        "shared": total,
        "head": head,
        "pending": len(prune(clone)),
        "lock_wait_s": waited,
        "fetch_lock_wait_s": round(fetch_waits, 3),
    }


def _progress(clone: Any) -> None:
    handle = events.locking.open_movable(clone.folder / PROGRESS_NAME)
    with os.fdopen(handle, "w", encoding="ascii") as stream:
        stream.write(uuid.uuid4().hex)
        stream.truncate()


def share(
    clone: Any,
    state: Path,
    *,
    plan: Plan,
    runner: Runner = git_runner.run,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, object]:

    started = clock()
    writer = vault_queue.writer_of(state)
    wait = plan.lock_wait or (
        _budget(plan, started, clock) if plan.urgent else vault_clone.LOCK_WAIT
    )
    asked = time.monotonic()
    lock = events.LedgerLock(clone.folder / SHARE_LOCK, timeout_s=wait)
    with contextlib.nullcontext() if plan.unlocked else lock:
        waited = round(time.monotonic() - asked, 3)
        if not prune(clone):
            return {"shared": 0, "pending": 0, "lock_wait_s": waited}
        attempt = total = 0
        rejected_head = ""
        fetch_waits = 0.0
        builder = _BatchBuilder(clone, writer, urgent=plan.urgent)

        def fetching(args: list[str], cwd: Path, **options: Any) -> str:
            if plan.urgent and args[0] == "fetch":
                options["timeout"] = min(float(options["timeout"]), _budget(plan, started, clock))
            return runner(args, cwd, **options)

        while True:
            attempt += 1
            _progress(clone)
            if attempt > 1 and plan.stop_when is not None and plan.stop_when():
                head = vault_clone._read(clone.folder / vault_clone.COVERS_NAME).strip()
                return _pending_share(clone, head, total, waited, fetch_waits)
            budget = _budget(plan, started, clock)
            fetched = _retry_head(clone, plan, fetching, budget, rejected_head) or _share_head(
                clone,
                plan,
                fetching,
                budget,
                fresh=attempt == 1 and plan.fresh,
            )
            head = str(fetched["head"])
            fetch_waits += float(fetched.get("fetch_lock_wait_s") or 0.0)
            if fetched.get("retracted") or vault_clone.unrepaired(clone, runner, budget):
                raise ShareError(
                    "the vault head dropped commits this clone had seen; "
                    "run fsck --repair --vault with the same vault, then sync again"
                )
            stop = vault_clone.ended(clone)
            if stop is not None:
                return _stopped(head, stop, clone)
            batch = [line for line in prune(clone) if line.get("writer") == writer]
            if not batch or (plan.stop_when is not None and plan.stop_when()):
                return _pending_share(clone, head, total, waited, fetch_waits)

            def git(args: list[str], **options: Any) -> str:
                return runner(args, clone.bare, timeout=_budget(plan, started, clock), **options)

            commit, batch = builder.latest(head, batch, git, lambda: _budget(plan, started, clock))
            if not batch or (plan.stop_when is not None and plan.stop_when()):
                return _pending_share(clone, head, total, waited, fetch_waits)
            try:
                _push(clone, commit, runner, _budget(plan, started, clock))
            except git_runner.GitRunnerError as exc:
                if "signature" in str(getattr(exc, "stderr", "")).lower():
                    raise ShareError(SIGNED_ONLY) from None
                rejected_head = head
                if _again(plan, attempt, started, clock):
                    continue
                raise (DeadlineError if plan.urgent else ShareError)(
                    f"the vault refused the share {attempt} times; "
                    f"{len(batch)} events stay queued; run sync again"
                ) from None
            vault_clone.durable(clone.folder / SHARED_AT, f"{plan.wall()}\n")
            budget = _budget(plan, started, clock)
            settled = _share_head(clone, plan, fetching, budget, fresh=True)
            fetch_waits += float(settled.get("fetch_lock_wait_s") or 0.0)
            total += len(batch)
            left = len(prune(clone))
            if left and plan.keep_going and _again(plan, attempt, started, clock):
                continue
            return {
                "shared": total,
                "head": commit,
                "pending": left,
                "lock_wait_s": waited,
                "fetch_lock_wait_s": round(fetch_waits, 3),
            }
