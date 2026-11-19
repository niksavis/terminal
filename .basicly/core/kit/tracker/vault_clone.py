from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable, Mapping
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
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_clone.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
events = _load("events.py", "basicly_tracker_kit_events")
vault_shapes = _load("vault_shapes.py", "basicly_tracker_kit_vault_shapes")
vault_config = _load("vault_config.py", "basicly_tracker_kit_vault_config")

STATE_NAME = "basicly-tracker"
STATE_VARIABLE = "BASICLY_TRACKER_STATE"
FETCH_REFSPEC = "+refs/heads/main:refs/remotes/origin/main"
HEAD_REF = "refs/remotes/origin/main"
SEEN_REF = "refs/basicly/seen"
RETRACTED_PREFIX = "refs/basicly/retracted/"
REPAIRED_NAME = "repaired"
FETCHED_NAME = "fetched"
FETCH_GENERATION_NAME = "fetch.generation"
VALID_NAME = "valid.ids"
EVENTS_NAME = "valid.jsonl"
COVERS_NAME = "valid.at"
QUARANTINE_NAME = "quarantine.jsonl"
ENDED_NAME = "ended.json"
WRITERS_NAME = "writers.json"
AFTER_ENDED = "ended: nothing after a valid end counts"
LOCK_WAIT = 2 * git_runner.DEFAULT_TIMEOUT + 10

Runner = Callable[..., str]


class CloneError(ValueError):
    pass


@dataclass(frozen=True)
class Clone:
    url: str
    folder: Path
    allow_file: bool

    @property
    def bare(self) -> Path:
        return self.folder / "clone"


def state_root(environ: Mapping[str, str], home: Path, *, windows: bool) -> Path:

    named = environ.get(STATE_VARIABLE, "")
    if named:
        if not Path(named).is_absolute():
            raise CloneError(f"{STATE_VARIABLE} must be an absolute path; it is {named!r}")
        return Path(named)
    base = environ.get("LOCALAPPDATA" if windows else "XDG_STATE_HOME", "")
    if base and Path(base).is_absolute():
        return Path(base) / STATE_NAME
    return home / ".local" / "state" / STATE_NAME


def _local_path(text: str) -> Path:
    if not text.startswith("file://"):
        return Path(text)
    rest = re.sub(r"%([0-9A-Fa-f]{2})", lambda hit: chr(int(hit.group(1), 16)), text[7:])
    return Path(rest[1:] if re.match(r"/[A-Za-z]:", rest) else rest)


def vault_source(text: str) -> tuple[str, bool]:

    path = _local_path(text)
    if path.is_dir():
        return path.resolve().as_uri(), True
    try:
        return git_runner.remote_url(text), False
    except git_runner.GitValueError:
        raise CloneError(
            f"--vault {text!r} is neither a local repository folder nor an https://, "
            "ssh:// or user@host:path address"
        ) from None


def _refuse_guarded_vault(vault: str) -> None:
    for root in events.records_guard_roots():
        config = vault_config.load(root)
        if config is None:
            continue
        named = {config.vault}
        with contextlib.suppress(CloneError):
            named.add(vault_source(config.vault)[0])
        if vault in named:
            events.refuse_records_in_ci(root / ".basicly")


def locate(state: Path, vault: str) -> Clone:
    _refuse_guarded_vault(vault)
    url, allow_file = vault_source(vault)
    name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return Clone(url, Path(state) / "vaults" / name, allow_file)


def private(path: Path) -> None:
    if os.name == "nt":
        permissions = _load("windows_permissions.py", "basicly_tracker_kit_windows_permissions")
        try:
            permissions.private(path)
        except permissions.DefaultOwnerError as error:
            raise CloneError(
                "Windows uses a default owner other than the current user. "
                "Run this tracker command under an account "
                "whose default owner is its current user. "
                "Preserve existing state and queued events."
            ) from error
        except OSError as error:
            raise CloneError(
                "Windows vault state is not private. "
                "Preserve its existing folder and queued events. "
                "Check the folder selected by --state or BASICLY_TRACKER_STATE. "
                "Correct its ownership and access lists before retrying."
            ) from error
        return
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def protect(clone: Clone) -> None:
    installer = _load("vault_push_hooks.py", "basicly_tracker_kit_vault_push_hooks")
    installer.install(clone.bare, owned=True)


def _ensure(clone: Clone, runner: Runner, timeout: float) -> None:

    if (clone.bare / "HEAD").is_file():
        protect(clone)
        return
    partial = clone.folder / "clone.partial"
    if partial.exists():
        shutil.rmtree(partial)
    runner(["init", "--bare", "-q", str(partial)], clone.folder, timeout=timeout)
    runner(["config", "remote.origin.url", clone.url], partial, timeout=timeout)
    runner(["config", "remote.origin.fetch", FETCH_REFSPEC], partial, timeout=timeout)
    partial.rename(clone.bare)
    protect(clone)


def ref(clone: Clone, name: str, runner: Runner, timeout: float) -> str:
    try:
        return runner(["rev-parse", "--verify", "-q", name], clone.bare, timeout=timeout).strip()
    except git_runner.GitCommandError:
        return ""


def _fetch_twice(clone: Clone, runner: Runner, timeout: float) -> bool:
    argv = ["fetch", "--quiet", "--no-tags", "origin", FETCH_REFSPEC]
    for _attempt in range(2):
        try:
            runner(argv, clone.bare, timeout=timeout, allow_file=clone.allow_file)
        except git_runner.GitRunnerError:
            continue
        return True
    return False


def durable(path: Path, text: str, *, append: bool = False) -> None:

    target = path if append else path.with_name(path.name + ".tmp")
    with target.open("a" if append else "w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    if not append:
        target.replace(path)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def ended(clone: Clone) -> dict[str, object] | None:
    text = _read(clone.folder / ENDED_NAME)
    return json.loads(text) if text else None


def writers(clone: Clone) -> dict[str, dict]:
    text = _read(clone.folder / WRITERS_NAME)
    return json.loads(text) if text else {}


def _latest(found: list) -> dict[str, dict]:
    return {
        str(event.get("writer")): {key: event.get(key) for key in ("id", "kind", "at")}
        for event in found
        if event.get("writer")
    }


def valid_events(clone: Clone) -> list[dict]:
    found: dict[str, dict] = {}
    for line in _read(clone.folder / EVENTS_NAME).splitlines():
        event = json.loads(line) if line else {}
        found.setdefault(str(event.get("id") or len(found)), event)
    return list(found.values())


def valid_ids(clone: Clone) -> set[str]:
    return set(_read(clone.folder / VALID_NAME).split())


def quarantine(clone: Clone) -> list[dict[str, object]]:
    found = [json.loads(line) for line in _read(clone.folder / QUARANTINE_NAME).splitlines()]
    return list({entry["commit"]: entry for entry in found}.values())


def _verdicts(
    clone: Clone, commits: list[str], stop: dict | None, parents: dict[str, list[str]]
) -> tuple:

    ids: list[str] = []
    found: list[dict] = []
    held: list[dict[str, object]] = []
    for commit in commits:
        verdict = (
            None if stop else vault_shapes.classify(clone.bare, commit, parents=parents[commit])
        )
        if verdict is None or not verdict.valid:
            held.append({"commit": commit, "rule": verdict.rule if verdict else AFTER_ENDED})
            continue
        ids += [str(event["id"]) for event in verdict.events if event.get("id")]
        found += list(verdict.events)
        stop = next((e for e in verdict.events if e.get("kind") == vault_shapes.STOP_KIND), None)
    return ids, held, stop, found


def retracted(clone: Clone, runner: Runner, timeout: float) -> dict[str, str]:
    listed = ["for-each-ref", "--format=%(refname) %(objectname)", RETRACTED_PREFIX]
    out = runner(listed, clone.bare, timeout=timeout)
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


def unrepaired(clone: Clone, runner: Runner, timeout: float) -> dict[str, str]:
    done = set(_read(clone.folder / REPAIRED_NAME).split())
    return {
        name: tip for name, tip in retracted(clone, runner, timeout).items() if name not in done
    }


def _retract(clone: Clone, tip: str, runner: Runner, timeout: float) -> None:
    held = retracted(clone, runner, timeout)
    if tip in held.values():
        return
    name = f"{RETRACTED_PREFIX}{len(held) + 1}"
    runner(["update-ref", name, tip, "0" * len(tip)], clone.bare, timeout=timeout)


def rebuild(
    clone: Clone, runner: Runner, timeout: float, *, keep_seen: bool = False
) -> dict[str, object]:

    (clone.folder / COVERS_NAME).unlink(missing_ok=True)
    if not keep_seen:
        runner(["update-ref", "-d", SEEN_REF], clone.bare, timeout=timeout)
    return _advance(clone, ref(clone, HEAD_REF, runner, timeout), runner, timeout)


def _advance(clone: Clone, head: str, runner: Runner, timeout: float) -> dict[str, object]:

    seen = ref(clone, SEEN_REF, runner, timeout)
    if seen and head == seen and _read(clone.folder / COVERS_NAME).strip() == seen:
        return {"seen": head, "moved": False, "retracted": False, "quarantined": []}
    parents = vault_shapes.first_parent_entries(clone.bare, head)
    chain = list(parents)
    if seen and seen not in chain:
        _retract(clone, seen, runner, timeout)
        return {"seen": seen, "moved": False, "retracted": True, "quarantined": []}
    whole = not seen or _read(clone.folder / COVERS_NAME).strip() != seen
    new = chain if whole else chain[chain.index(seen) + 1 :]
    ids, held, stop, found = _verdicts(clone, new, None if whole else ended(clone), parents)
    lines = "".join(json.dumps(event, sort_keys=True) + "\n" for event in found)
    durable(clone.folder / EVENTS_NAME, lines, append=not whole)
    durable(clone.folder / VALID_NAME, "".join(f"{i}\n" for i in ids), append=not whole)
    lines = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in held)
    durable(clone.folder / QUARANTINE_NAME, lines, append=not whole)
    if stop is not None or whole:
        durable(clone.folder / ENDED_NAME, json.dumps(stop) if stop else "")
    known = {} if whole else writers(clone)
    durable(clone.folder / WRITERS_NAME, json.dumps({**known, **_latest(found)}, sort_keys=True))
    durable(clone.folder / COVERS_NAME, f"{head}\n")
    if head != seen:
        runner(["update-ref", SEEN_REF, head, seen or "0" * len(head)], clone.bare, timeout=timeout)
    return {"seen": head, "moved": head != seen, "retracted": False, "quarantined": held}


def settle(
    clone: Clone,
    *,
    runner: Runner = git_runner.run,
    timeout: float = git_runner.DEFAULT_TIMEOUT,
    lock_wait: float = LOCK_WAIT,
) -> dict[str, object]:

    asked = time.monotonic()
    with events.LedgerLock(clone.folder / "fetch", timeout_s=lock_wait):
        waited = round(time.monotonic() - asked, 3)
        shown = _advance(clone, ref(clone, HEAD_REF, runner, timeout), runner, timeout)
    return {**shown, "fetch_lock_wait_s": waited}


@dataclass(frozen=True)
class Fetch:
    clock: Callable[[], float]
    runner: Runner = git_runner.run
    timeout: float = git_runner.DEFAULT_TIMEOUT
    lock_wait: float = LOCK_WAIT
    coalesce: bool = False
    previous_generation: str | None = None


def fetch(
    clone: Clone,
    *,
    runner: Runner = git_runner.run,
    timeout: float = git_runner.DEFAULT_TIMEOUT,
    lock_wait: float = LOCK_WAIT,
    clock: Callable[[], float],
) -> dict[str, object]:
    return fetch_with(clone, Fetch(clock, runner, timeout, lock_wait))


def _covered_head(clone: Clone, runner: Runner, timeout: float) -> str:
    head = ref(clone, HEAD_REF, runner, timeout)
    if (
        head
        and _read(clone.folder / COVERS_NAME).strip() == head
        and ref(clone, SEEN_REF, runner, timeout) == head
    ):
        return head
    return ""


def _advanced_head(clone: Clone, previous: str, runner: Runner, timeout: float) -> str:
    try:
        with events.LedgerLock(clone.folder / "fetch", timeout_s=0):
            covered = _read(clone.folder / COVERS_NAME).strip()
            if not covered or covered == previous:
                return ""
            head = _covered_head(clone, runner, timeout)
            return head if head != previous else ""
    except events.LockUnavailableError:
        return ""


def fetch_with(clone: Clone, request: Fetch) -> dict[str, object]:
    _refuse_guarded_vault(clone.url)

    runner, timeout, lock_wait, clock, coalesce = (
        request.runner,
        request.timeout,
        request.lock_wait,
        request.clock,
        request.coalesce,
    )

    private(clone.folder.parent.parent)
    private(clone.folder)
    stamp = clone.folder / FETCHED_NAME
    generation = clone.folder / FETCH_GENERATION_NAME
    before = request.previous_generation
    if before is None:
        before = _read(generation) if coalesce else ""
    asked = time.monotonic()
    with events.LedgerLock(clone.folder / "fetch", timeout_s=lock_wait):
        waited = round(time.monotonic() - asked, 3)
        _ensure(clone, runner, timeout)
        latest = _read(generation) if coalesce else ""
        joined = bool(latest and latest != before)
        if joined:
            try:
                git_runner.writer_id(latest.strip())
            except git_runner.GitValueError:
                joined = False
        covered = _covered_head(clone, runner, timeout) if joined else ""
        joined = bool(covered)
        fetched = joined or _fetch_twice(clone, runner, timeout)
        head = covered if joined else ref(clone, HEAD_REF, runner, timeout)
        if not head:
            raise CloneError(f"could not fetch {clone.url} and no earlier fetch exists; retry")
        if joined:
            seen = {"seen": head, "moved": False}
        elif fetched:
            stamp.write_text(f"{clock()}\n", encoding="utf-8")
            seen = _advance(clone, head, runner, timeout)
            durable(generation, git_runner.new_writer_id() + "\n")
        else:
            seen = {"seen": ref(clone, SEEN_REF, runner, timeout), "moved": False}
    stamped = _read(stamp).strip()
    age = round(max(0.0, clock() - float(stamped)), 1) if stamped else None
    return {
        "clone": str(clone.bare),
        "head": head,
        "fetched": fetched,
        "age_s": age,
        "fetch_lock_wait_s": waited,
        **({"coalesced": True} if joined else {}),
        **seen,
    }
