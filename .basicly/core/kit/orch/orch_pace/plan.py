from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orch_pace.snapshot import Window

HOUR_S = 3600
LENGTH_S = {"five_hour": 5 * HOUR_S, "seven_day": 7 * 24 * HOUR_S}
STALE_S = 600
RECENT_S = HOUR_S
FIT_FROM_S = 600
FIT_TO_S = 1800
MIN_SPAN_S = 900
MIN_ELAPSED_S = {"five_hour": 30 * 60, "seven_day": 24 * HOUR_S}
HOLD_AT = 90.0
CLOSE_AT = 100.0
USED_CLOSE_AT = 95.0
ADVICE = ("start", "hold", "close idle")
RECENT = "last 60 min"
AVERAGE = "window average"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Pace:
    name: str
    used: float
    resets_at: int
    read_at: int
    rate: float | None
    basis: str
    projected: float
    advice: str
    over: bool


def _num(window: Window, key: str) -> float:
    value = window[key]
    return float(value) if isinstance(value, int | float) else 0.0


def _readings(window: Window) -> list[tuple[float, float]]:
    found = window.get("readings")
    return [(float(r[0]), float(r[1])) for r in found] if isinstance(found, list) else []


def rate(name: str, window: Window, now: int) -> tuple[float | None, str]:
    used, resets = _num(window, "used_percentage"), _num(window, "resets_at")
    if name == "five_hour":
        recent = [r for r in _readings(window) if now - r[0] <= RECENT_S]
        if len(recent) >= 2 and recent[-1][0] - recent[0][0] >= MIN_SPAN_S:
            span = recent[-1][0] - recent[0][0]
            return (recent[-1][1] - recent[0][1]) * HOUR_S / span, RECENT
    elapsed = now - (resets - LENGTH_S[name])
    if elapsed >= MIN_ELAPSED_S[name]:
        return used * HOUR_S / elapsed, AVERAGE
    return None, UNKNOWN


def advise(used: float, projected: float) -> str:
    if projected >= CLOSE_AT or used >= USED_CLOSE_AT:
        return "close idle"
    if projected >= HOLD_AT:
        return "hold"
    return "start"


def pace(name: str, window: Window, now: int) -> Pace:
    used, resets, read = (_num(window, k) for k in ("used_percentage", "resets_at", "read_at"))
    if resets <= now:
        return Pace(name, 0.0, int(resets), int(read), None, UNKNOWN, 0.0, "start", True)
    found, basis = rate(name, window, now)
    projected = used + (found or 0.0) * (resets - now) / HOUR_S
    return Pace(
        name, used, int(resets), int(read), found, basis, projected, advise(used, projected), False
    )


@dataclass(frozen=True)
class Fit:
    needed: float
    burn: float
    working: int
    count: int


def measure(window: Window, now: int, working: int) -> tuple[Fit | None, str]:
    used, resets = _num(window, "used_percentage"), _num(window, "resets_at")
    if resets <= now:
        return None, "the window reset and has no reading yet"
    if working < 1:
        return None, "no session is working"
    recent = [r for r in _readings(window) if now - r[0] <= FIT_TO_S]
    if len(recent) < 2 or recent[-1][0] - recent[0][0] < FIT_FROM_S:
        return None, f"readings of the last {FIT_TO_S // 60} min span under {FIT_FROM_S // 60} min"
    taken = recent[-1][0] - recent[0][0]
    burn = (recent[-1][1] - recent[0][1]) * HOUR_S / taken
    if burn <= 0:
        return None, "no use measured in the last readings"
    needed = (CLOSE_AT - used) * HOUR_S / (resets - now)
    basis = f"burn {burn:.1f}%/h over the last {int(taken // 60)} min with {working} working"
    return Fit(needed, burn, working, int(needed * working // burn)), basis


def fit(window: Window, now: int, working: int) -> tuple[int | None, str]:
    found, basis = measure(window, now, working)
    return (found.count if found else None), basis


def needed_rate(window: Window, now: int) -> float:
    used, resets = _num(window, "used_percentage"), _num(window, "resets_at")
    if resets <= now:
        return CLOSE_AT * HOUR_S / LENGTH_S["five_hour"]
    return (CLOSE_AT - used) * HOUR_S / (resets - now)


def _verb(count: int, working: int) -> str:
    change = count - working
    if change > 0:
        return f"start {change} more"
    if change == 0:
        return f"hold at {working}"
    return f"start none; let {-change} of {working} finish"


def sessions_line(window: Window, now: int, working: int, assumed: float) -> str:
    found, basis = measure(window, now, working)
    if found is not None:
        return (
            f"sessions: {_verb(found.count, found.working)} (needed {found.needed:.1f}%/h until "
            f"the reset, {found.burn / found.working:.1f}%/h per working session, "
            f"{found.working} working, {found.count} fit)"
        )
    needed = needed_rate(window, now)
    count = int(needed // assumed)
    return (
        f"sessions: {_verb(count, working)} (assumed {assumed:g}%/h per session from config; "
        f"needed {needed:.1f}%/h until the reset, {working} working, {count} fit; "
        f"no measured burn: {basis})"
    )


def fit_line(window: Window, now: int, working: int) -> str:
    count, basis = fit(window, now, working)
    if count is None:
        return f"fit: unknown ({basis})"
    noun = "session fits" if count == 1 else "sessions fit"
    return f"fit: {count} working {noun} until the reset ({basis})"


def overall(paces: list[Pace]) -> str:
    return max((p.advice for p in paces), key=ADVICE.index, default="hold")


def when(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M UTC")


def span(seconds: float) -> str:
    minutes = max(0, int(seconds // 60))
    days, rest = divmod(minutes, 24 * 60)
    hours, mins = divmod(rest, 60)
    return f"{days}d{hours}h" if days else f"{hours}h{mins:02d}m"


def line(p: Pace, now: int) -> str:
    if p.over:
        reset = when(p.resets_at)
        return f"{p.name}: window reset at {reset}; no reading of the new window yet; start"
    shown = f"{p.rate:.1f}%/h ({p.basis})" if p.rate is not None else "unknown (window too young)"
    return (
        f"{p.name}: used {p.used:.1f}%, resets {when(p.resets_at)} (in {span(p.resets_at - now)}), "
        f"burn {shown}, at reset {p.projected:.1f}%, read {span(now - p.read_at)} ago; {p.advice}"
    )
