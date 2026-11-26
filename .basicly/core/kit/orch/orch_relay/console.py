from __future__ import annotations

import contextlib
import importlib
import json
import os
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orch_lessons.log import RefusedError
from orch_state import store

if TYPE_CHECKING:
    import runner

FILE = "console.json"
LEDGER = "spend.jsonl"
LOCK = "spend.lock"
LOCK_WAIT = 60.0
BILLINGS = ("subscription", "console")
MODES = ("bare", "profile")
SHAPE = (
    '{"settings": SETTINGS_FILE, "profile": PROFILE_DIR, "run_cap_usd": 0.5, '
    '"month_budget_usd": 100, "tiers": {"cheap": {"model": "haiku", "effort": "low", '
    '"mode": "bare"}}}'
)
ENTRY = (
    "id",
    "state",
    "at",
    "month",
    "record",
    "session",
    "tier",
    "model",
    "mode",
    "cost_usd",
    "estimated",
)


@dataclass(frozen=True)
class Plan:
    tier: str
    model: str
    effort: str
    mode: str
    cap: float
    budget: float
    place: str


def _refuse_setting(path: Path, key: str) -> RefusedError:
    return RefusedError(
        f"orch delegate --billing console: the Console config {path} has no valid {key!r}; "
        f"write it in this shape: {SHAPE}"
    )


def _number(path: Path, value: dict[str, Any], key: str) -> float:
    found = value.get(key)
    if isinstance(found, bool) or not isinstance(found, int | float) or found <= 0:
        raise _refuse_setting(path, key)
    return float(found)


def load(base: Path) -> dict[str, Any]:
    path = base / FILE
    if not path.is_file():
        raise RefusedError(
            f"orch delegate --billing console: no Console config at {path}; write it in this "
            f"shape: {SHAPE}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RefusedError(f"the Console config {path} is not readable JSON; fix it") from error
    if not isinstance(value, dict):
        raise _refuse_setting(path, "tiers")
    return value


def _tier(path: Path, tiers: dict[str, Any], name: str) -> dict[str, str]:
    found = tiers.get(name)
    keys = ("model", "effort", "mode")
    if not isinstance(found, dict) or not all(isinstance(found.get(k), str) for k in keys):
        raise _refuse_setting(path, f"tiers.{name}")
    if found["mode"] not in MODES:
        raise RefusedError(
            f"the tier {name!r} in {path} has the mode {found['mode']!r}; use one of: "
            f"{', '.join(MODES)}"
        )
    return found


def _pick(path: Path, tiers: dict[str, Any], tier: str | None, model: str | None) -> str:
    if tier:
        if tier not in tiers:
            raise RefusedError(
                f"--tier {tier!r} is not in the Console config {path}; use one of: "
                f"{', '.join(sorted(tiers))}"
            )
        return tier
    if not model:
        raise RefusedError(
            f"orch delegate --billing console needs --tier or --model; the tiers in {path} are: "
            f"{', '.join(sorted(tiers))}"
        )
    named = sorted(
        n for n in tiers if isinstance(tiers[n], dict) and tiers[n].get("model") == model
    )
    allowed = sorted({str(t.get("model")) for t in tiers.values() if isinstance(t, dict)})
    if not named:
        raise RefusedError(
            f"--model {model!r} is not allowed by the Console config {path}; allowed models: "
            f"{', '.join(allowed)}"
        )
    if len(named) > 1:
        raise RefusedError(
            f"--model {model!r} is in the tiers {', '.join(named)} of {path}; pass --tier"
        )
    return named[0]


def plan(base: Path, tier: str | None, model: str | None, read_only: bool) -> Plan:
    path = base / FILE
    value = load(base)
    tiers = value.get("tiers")
    if not isinstance(tiers, dict) or not tiers:
        raise _refuse_setting(path, "tiers")
    name = _pick(path, tiers, tier, model)
    found = _tier(path, tiers, name)
    mode = found["mode"]
    if mode == "bare" and not read_only:
        raise RefusedError(
            f"the tier {name!r} runs bare, which skips hooks; bare is for --read-only work, so "
            f"use a tier with the mode profile for a lane turn"
        )
    if mode == "profile" and read_only:
        raise RefusedError(
            f"the tier {name!r} runs in a profile, which needs a lane; drop --read-only or use "
            f"a tier with the mode bare"
        )
    key = "settings" if mode == "bare" else "profile"
    place = value.get(key)
    if not isinstance(place, str) or not place:
        raise _refuse_setting(path, key)
    exists = Path(place).is_file() if mode == "bare" else Path(place).is_dir()
    if not exists:
        raise RefusedError(f"the Console {key} {place} named in {path} does not exist")
    cap, budget = _number(path, value, "run_cap_usd"), _number(path, value, "month_budget_usd")
    return Plan(name, found["model"], found["effort"], mode, cap, budget, place)


def month() -> str:
    return store.utc_now().strftime("%Y-%m")


def _try_lock(handle: int) -> bool:
    try:
        if os.name == "nt":
            msvcrt = importlib.import_module("msvcrt")
            os.lseek(handle, 0, os.SEEK_SET)
            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
        else:
            fcntl = importlib.import_module("fcntl")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def _locked(base: Path) -> Iterator[None]:
    base.mkdir(parents=True, exist_ok=True)
    path = base / LOCK
    handle = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + LOCK_WAIT
        while not _try_lock(handle):
            if time.monotonic() > deadline:
                raise RefusedError(
                    f"the spend ledger lock {path} stayed held for {LOCK_WAIT:.0f} s; another "
                    f"orch delegate is reserving its run, so try again"
                )
            time.sleep(0.1)
        yield
    finally:
        os.close(handle)


def _entry(line: str) -> dict[str, Any] | None:
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    if not isinstance(entry, dict) or "id" not in entry:
        return None
    cost = entry.get("cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        return None
    return entry


def _entries(path: Path) -> dict[str, dict[str, Any]]:
    folded: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return folded
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        entry = _entry(line)
        if entry is None:
            raise RefusedError(
                f"the spend ledger {path} line {number} is not a spend entry; fix it, because "
                f"a skipped line under-counts the spend"
            )
        folded[str(entry["id"])] = entry
    return folded


def spent(base: Path, when: str) -> float:
    entries = _entries(base / LEDGER).values()
    return sum(float(e["cost_usd"]) for e in entries if e.get("month") == when)


def refuse_budget(base: Path, found: Plan) -> None:
    when = month()
    used = spent(base, when)
    if used + found.cap > found.budget:
        raise RefusedError(
            f"console budget: {used:.4f} USD spent in {when} of the {found.budget:.2f} USD month "
            f"budget; a run may cost up to {found.cap:.2f} USD, so orch delegate starts none"
        )


def refuse_place(found: Plan, cwd: Path) -> None:
    if found.mode == "profile" and not (cwd / ".git").is_file():
        raise RefusedError(
            f"the tier {found.tier!r} runs in a profile, and {cwd} is not a linked git worktree; "
            f"run it in a lane made with basicly worktree create"
        )


def argv(found: Plan, given: list[str]) -> list[str]:
    tail = ["--max-budget-usd", f"{found.cap:g}", "--effort", found.effort]
    if found.mode == "bare":
        tail += ["--bare", "--settings", found.place]
    return [*given, *tail]


def env(found: Plan) -> dict[str, str] | None:
    if found.mode == "bare":
        return None
    return {**os.environ, "CLAUDE_CONFIG_DIR": found.place}


def cost(done: runner.Done) -> float | None:
    try:
        shown = json.loads(done.out)
    except ValueError:
        return None
    found = shown.get("total_cost_usd") if isinstance(shown, dict) else None
    if isinstance(found, bool) or not isinstance(found, int | float):
        return None
    return float(found)


@dataclass(frozen=True)
class Run:
    plan: Plan
    key: str
    record: str
    session: str
    when: str


def _append(base: Path, run: Run, state: str, value: float, estimated: bool) -> None:
    shown = (store.utc_now().isoformat(timespec="seconds"), run.when, run.record, run.session)
    picked = (run.plan.tier, run.plan.model, run.plan.mode, value, estimated)
    entry = dict(zip(ENTRY, (run.key, state, *shown, *picked), strict=True))
    with (base / LEDGER).open("a", encoding="utf-8") as out:
        out.write(json.dumps(entry, sort_keys=True) + "\n")


def reserve(base: Path, found: Plan, record: str, session: str) -> Run:
    with _locked(base):
        refuse_budget(base, found)
        run = Run(found, uuid.uuid4().hex, record, session, month())
        _append(base, run, "pending", found.cap, True)
    return run


def settle(base: Path, run: Run, done: runner.Done) -> str:
    measured = cost(done)
    value = run.plan.cap if measured is None else measured
    with _locked(base):
        _append(base, run, "settled", value, measured is None)
        total = spent(base, run.when)
    kind = "estimated at the run cap" if measured is None else "measured"
    return (
        f"spend: {value:.6f} USD this run ({kind}); {total:.4f} of {run.plan.budget:.2f} USD "
        f"in {run.when}"
    )
