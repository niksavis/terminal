from __future__ import annotations

from datetime import datetime, timedelta

from orch_lessons.log import Clock, RefusedError, utc_now

from orch_relay import messages

ASK = "ask the Orchestrator for a new relay"
ACTION = "Exact action:"
ENDS = (
    "Risks and their checks:",
    "Reason:",
    "Condition:",
    "Proof command:",
    "If the proof fails:",
    "Council run:",
    "Good for ",
    messages.UNTIL_LANDED,
)
KINDS = {"[decision ": "decision", "[approval ": "approval"}
AUTHORITY = {
    "decision": "Rule that lets the orchestrator decide ask-first items (",
    "approval": "The person's words at ",
}
EARLY = timedelta(minutes=5)


def _refuse(why: str) -> RefusedError:
    return RefusedError(f"orch accept refuses: {why}; {ASK}")


def _value(lines: list[str], label: str) -> str | None:
    found = next((line for line in lines if line.startswith(label)), None)
    return found[len(label) :].strip() if found is not None else None


def _action(lines: list[str]) -> str | None:
    if ACTION not in lines:
        return None
    body: list[str] = []
    for line in lines[lines.index(ACTION) + 1 :]:
        if line.startswith(ENDS):
            break
        body.append(line.rstrip())
    return "\n".join(body).strip()


def _same(name: str, said: str | None, wanted: str) -> None:
    if said is None:
        raise _refuse(f"the relay names no {name}")
    if said != wanted.strip():
        raise _refuse(f"the relay names {name} {said!r}, not {wanted.strip()!r}")


def _stamp(head: str, kind: str, lines: list[str]) -> datetime:
    said = head.split(" ", 1)[1].split("]", 1)[0] if "]" in head else ""
    if kind == "decision" and _value(lines, "Entry stamp:") != said:
        raise _refuse("the entry stamp is missing or differs from the decision line")
    try:
        when = datetime.fromisoformat(said)
    except ValueError:
        raise _refuse(f"the stamp {said!r} is not a time") from None
    if when.tzinfo is None:
        raise _refuse(f"the stamp {said!r} has no time zone")
    return when


def check(text: str, record: str, repo: str, action: str, clock: Clock = utc_now) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    head = lines[0] if lines else ""
    kind = next((name for mark, name in KINDS.items() if head.startswith(mark)), None)
    if kind is None:
        raise _refuse("the text is not a relayed decision or approval")
    if not any(line.startswith(AUTHORITY[kind]) for line in lines):
        raise _refuse(
            f"the {kind} names no {'rule and its date' if kind == 'decision' else 'words'}"
        )
    when = _stamp(head, kind, lines)
    _same("record", _value(lines, "Record:"), record)
    _same("target repository", _value(lines, "Target repository:"), repo)
    _same("exact action", _action(lines), action)
    if messages.UNTIL_LANDED in lines:
        return f"accepted {kind} for {record} in {repo}: good for this exact diff until it lands"
    now = clock()
    until = when + timedelta(minutes=messages.VALID_FOR_MINUTES)
    if when - now > EARLY:
        raise _refuse(f"the stamp {when.isoformat()} is in the future")
    if now > until:
        raise _refuse(f"it expired at {until.isoformat(timespec='minutes')}")
    ends = until.isoformat(timespec="minutes")
    return f"accepted {kind} for {record} in {repo}: good for one use until {ends}"
