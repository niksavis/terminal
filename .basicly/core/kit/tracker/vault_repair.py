from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_repair.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_share = _load("vault_share.py", "basicly_tracker_kit_vault_share")
vault_fold = _load("vault_fold.py", "basicly_tracker_kit_vault_fold")
shapes = vault_clone.vault_shapes

PROCESSED_NAME = "quarantine.done"
REQUEUE = "requeue"
CLAIM_LOST = "claim-lost"
TIMEOUT = git_runner.DEFAULT_TIMEOUT

Runner = Callable[..., str]


class RepairError(ValueError):
    pass


def _read(path: Path) -> set[str]:
    return set(path.read_text(encoding="utf-8").split()) if path.exists() else set()


def _git(clone: Any, runner: Runner) -> Callable[..., str]:
    def git(args: list[str]) -> str:
        return runner(args, clone.bare, timeout=TIMEOUT)

    return git


def report(clone: Any, *, runner: Runner = git_runner.run) -> dict[str, object]:

    done = _read(clone.folder / vault_clone.REPAIRED_NAME)
    processed = _read(clone.folder / PROCESSED_NAME)
    return {
        "head": vault_clone.ref(clone, vault_clone.HEAD_REF, runner, TIMEOUT),
        "seen": vault_clone.ref(clone, vault_clone.SEEN_REF, runner, TIMEOUT),
        "retracted": [
            {"ref": name, "tip": tip, "repaired": name in done}
            for name, tip in sorted(vault_clone.retracted(clone, runner, TIMEOUT).items())
        ],
        "quarantined": [
            {**entry, "processed": entry["commit"] in processed}
            for entry in vault_clone.quarantine(clone)
        ],
        "pending": len(vault_queue.pending(clone.folder / vault_queue.QUEUE_NAME)),
    }


def _parse(text: str) -> list[dict]:
    found = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("kind") != shapes.SEGMENT_KIND:
            found.append(value)
    return found


def _blob(git: Callable[..., str], commit: str, path: str) -> str:
    try:
        return git(["cat-file", "blob", f"{commit}:{path}"])
    except git_runner.GitCommandError:
        return ""


def added_lines(git: Callable[..., str], commit: str) -> list[dict]:

    parents = git(["rev-list", "--parents", "-n", "1", commit]).split()[1:2]
    base = parents[0] if parents else ""
    listed = ["diff-tree", "-r", "--no-commit-id", "--name-only", *(parents or ["--root"])]
    paths = git([*listed, commit, "--", f"{shapes.LOG_ROOT}/"]).split()
    found: list[dict] = []
    for path in paths:
        new = _blob(git, commit, path)
        old = _blob(git, base, path) if base else ""
        found += _parse(new.removeprefix(old))
    return found


def _lost(clone: Any, git: Callable[..., str], tips: Iterable[str], entries: list) -> list[dict]:

    head = git(["rev-parse", vault_clone.HEAD_REF]).strip()
    on_head = set(shapes.first_parent_chain(clone.bare, head))
    lines: list[dict] = []
    for tip in tips:
        for commit in shapes.first_parent_chain(clone.bare, tip):
            verdict = None if commit in on_head else shapes.classify(clone.bare, commit)
            lines += list(verdict.events) if verdict is not None and verdict.valid else []
    for entry in entries:
        lines += added_lines(git, str(entry["commit"]))
    valid = vault_clone.valid_ids(clone)
    unique = {str(line.get("id")): line for line in lines if line.get("id")}
    return [line for key, line in unique.items() if key not in valid]


def _claims_lost(clone: Any, lost: list[dict]) -> list[dict[str, object]]:

    head = vault_clone.ref(clone, vault_clone.HEAD_REF, git_runner.run, TIMEOUT)
    folded = vault_fold.fold(shapes.valid_events(shapes.check(clone.bare, head)))
    gone = []
    for line in lost:
        if line.get("kind") not in (vault_fold.CLAIM, vault_fold.TAKE):
            continue
        state = folded.records.get(str(line.get("record")))
        wanted = (str(line.get("writer") or ""), str(line.get("session") or ""))
        if state is None or state.holder != wanted:
            gone.append({
                "kind": CLAIM_LOST,
                "record": line.get("record"),
                "payload": {
                    "claim": line.get("id"),
                    "writer": line.get("writer"),
                    "name": vault_fold.holder_name_of(line),
                },
            })
    return gone


def repair(
    clone: Any, state: Path, *, clock: Callable[[], float], runner: Runner = git_runner.run
) -> dict[str, object]:

    writer = vault_queue.writer_of(state)
    git = _git(clone, runner)
    with events.LedgerLock(clone.folder / vault_share.SHARE_LOCK):
        with events.LedgerLock(clone.folder / "fetch"):
            refs = vault_clone.unrepaired(clone, runner, TIMEOUT)
            processed = _read(clone.folder / PROCESSED_NAME)
            entries = [e for e in vault_clone.quarantine(clone) if e["commit"] not in processed]
            vault_clone.rebuild(clone, runner, TIMEOUT)
            lost = _lost(clone, git, refs.values(), entries)
        own = [line for line in lost if line.get("writer") == writer]
        others = [line for line in lost if line.get("writer") != writer]
        drafts = _claims_lost(clone, lost)
        if others:
            drafts.append({"kind": REQUEUE, "payload": {"events": others}})
        requeued = vault_queue.requeue(clone, own)
        if drafts:
            origin = vault_queue.Origin("repair", False, clock)
            vault_queue.write(clone, drafts, state=state, origin=origin)
        vault_clone.durable(clone.folder / vault_clone.REPAIRED_NAME, _lines(refs), append=True)
        commits = [str(e["commit"]) for e in entries]
        vault_clone.durable(clone.folder / PROCESSED_NAME, _lines(commits), append=True)
    return {
        "requeued": requeued,
        "requeue_event": len(others),
        "claim_lost": sum(1 for d in drafts if d["kind"] == CLAIM_LOST),
        "repaired": sorted(refs),
        "processed": commits,
    }


def _lines(values: Iterable[str]) -> str:
    return "".join(f"{value}\n" for value in values)


def accept_rewrite(
    clone: Any, head: str, *, purge: bool, runner: Runner = git_runner.run
) -> dict[str, object]:

    if not purge:
        raise RepairError("--accept-rewrite drops every retracted ref; pass --purge to confirm")
    with events.LedgerLock(clone.folder / "fetch"):
        current = vault_clone.ref(clone, vault_clone.HEAD_REF, runner, TIMEOUT)
        if head != current:
            raise RepairError(f"--accept-rewrite must name the fetched head {current}; fetch first")
        refs = vault_clone.retracted(clone, runner, TIMEOUT)
        for name in refs:
            runner(["update-ref", "-d", name], clone.bare, timeout=TIMEOUT)
        (clone.folder / vault_clone.REPAIRED_NAME).unlink(missing_ok=True)
        vault_clone.rebuild(clone, runner, TIMEOUT)
    return {"purged": sorted(refs), "head": current}


def reclone(
    clone: Any, *, clock: Callable[[], float], runner: Runner = git_runner.run
) -> dict[str, object]:

    old = clone.folder / "clone.old"
    with events.LedgerLock(clone.folder / vault_share.SHARE_LOCK):
        with events.LedgerLock(clone.folder / "fetch"):
            if old.exists():
                shutil.rmtree(old)
            clone.bare.rename(old)
        vault_clone.fetch(clone, clock=clock, runner=runner)
        with events.LedgerLock(clone.folder / "fetch"):
            copied = [
                "fetch",
                "--no-tags",
                old.resolve().as_uri(),
                "+refs/basicly/*:refs/basicly/*",
            ]
            runner(copied, clone.bare, timeout=TIMEOUT, allow_file=True)
            shown = vault_clone.rebuild(clone, runner, TIMEOUT, keep_seen=True)
            refs = runner(["for-each-ref", "--format=%(refname)", "refs/basicly/"], clone.bare)
        shutil.rmtree(old)
    return {"clone": str(clone.bare), "refs": refs.split(), **shown}


def check(
    clone: Any, state: Path, args: Mapping[str, Any], clock: Callable[[], float]
) -> dict[str, object]:

    if args.get("accept_rewrite"):
        return accept_rewrite(clone, args["accept_rewrite"], purge=bool(args.get("purge")))
    if args.get("repair"):
        return repair(clone, state, clock=clock)
    return report(clone)
