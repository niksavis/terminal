from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orch_lessons.log import Clock, RefusedError, check_text, utc_now

from orch_relay import classes, fields, local_sets

if TYPE_CHECKING:
    from orch_relay.record import Tracker

VALID_FOR_MINUTES = 60
UNTIL_LANDED = "Good for this exact diff until it lands; any change to the diff voids it."
REPORT_STATES = ("working", "done", "blocked", "needs-decision")
RULE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
PROJECT_RECORD = "Project record:"

Scan = Callable[[str], str | None]


def stamp(clock: Clock) -> str:
    return clock().isoformat(timespec="seconds")


def _risk_lines(parsed: list[fields.Risk]) -> list[str]:
    return [f"- risk: {item.risk}; check: {item.check}" for item in parsed]


@dataclass(frozen=True)
class Action:
    item: str
    record: str
    repo: str
    action: str
    risks: list[str] = field(default_factory=list)
    project_record: str = ""


def _action_lines(act: Action, parsed: list[fields.Risk]) -> list[str]:
    return [
        f"Record: {act.record}",
        *([f"{PROJECT_RECORD} {act.project_record}"] if act.project_record else []),
        f"Item: {act.item}",
        f"Target repository: {act.repo}",
        "Exact action:",
        act.action,
        *(["Risks and their checks:", *_risk_lines(parsed)] if parsed else []),
    ]


@dataclass(frozen=True)
class Decision:
    rule: str
    rule_date: str
    reason: str
    condition: str
    proof: str
    if_proof_fails: str
    council: str = ""


@dataclass(frozen=True)
class Writer:
    tracker: Tracker
    scan: Scan
    clock: Clock = utc_now
    session: str = ""

    def _record_and_send(self, record: str, comment: str) -> str:
        check_text(self.scan, [comment])
        self.tracker.comment(record, comment)
        return comment

    def decide(self, act: Action, why: Decision) -> str:
        rule, rule_date, reason = why.rule, why.rule_date, why.reason
        condition, proof, if_proof_fails = why.condition, why.proof, why.if_proof_fails
        given = {
            "item": act.item,
            "record": act.record,
            "repo": act.repo,
            "action": act.action,
            "rule": rule,
            "rule-date": rule_date,
            "reason": reason,
            "condition": condition,
            "proof": proof,
            "if-proof-fails": if_proof_fails,
        }
        fields.require(given, "orch decide")
        local_sets.refuse(act.action, "--action")
        local_sets.refuse(proof, "--proof")
        if not RULE_DATE.fullmatch(rule_date.strip()):
            raise RefusedError("orch decide refuses --rule-date: write it as YYYY-MM-DD")
        classes.require_class(
            act.item, frozenset({classes.ASK_FIRST, classes.COUNCIL_DECIDES}), "orch decide"
        )
        council = why.council.strip()
        if classes.item_class(act.item) == classes.COUNCIL_DECIDES and not council:
            raise RefusedError(
                f"orch decide refuses {act.item!r} without --council: name the council run "
                'that decided it (at least three blind voters) and its result, "<run id>: <result>"'
            )
        if council:
            given["council"] = council
        if act.project_record:
            given["project-record"] = act.project_record
        fields.no_placeholder(given, "orch decide")
        parsed = fields.risks(act.risks, act.action, "orch decide")
        now = stamp(self.clock)
        text = "\n".join([
            f"[decision {now}] Orchestrator decision on an ask-first item.",
            *([self.session] if self.session else []),
            f'Rule that lets the orchestrator decide ask-first items ({rule_date}): "{rule}"',
            f"Entry stamp: {now}",
            *_action_lines(act, parsed),
            f"Reason: {reason}",
            f"Condition: {condition}",
            f"Proof command: {proof}",
            f"If the proof fails: {if_proof_fails}",
            *([f"Council run: {council}"] if council else []),
            f"Good for one use, within {VALID_FOR_MINUTES} minutes of {now}.",
        ])
        return self._record_and_send(act.record, text)

    def approve(self, act: Action, words: str, diff: bool = False) -> str:
        given = {
            "item": act.item,
            "record": act.record,
            "repo": act.repo,
            "action": act.action,
            "words": words,
        }
        fields.require(given, "orch approve")
        classes.require_class(
            act.item, frozenset({classes.PERSON_APPROVES, classes.COUNCIL_DECIDES}), "orch approve"
        )
        once = classes.item_class(act.item) == classes.COUNCIL_DECIDES
        if once and diff:
            raise RefusedError(
                f"orch approve refuses --diff for {act.item!r}: the person's approval of a "
                "test, gate or hook change is good for one use; leave out --diff"
            )
        if act.project_record:
            given["project-record"] = act.project_record
        fields.no_placeholder({k: v for k, v in given.items() if k != "words"}, "orch approve")
        parsed = fields.risks(act.risks, act.action, "orch approve")
        now = stamp(self.clock)
        text = "\n".join([
            f"[approval {now}] The person's approval, relayed by the orchestrator.",
            *([self.session] if self.session else []),
            f'The person\'s words at {now}: "{words}"',
            *_action_lines(act, parsed),
            UNTIL_LANDED
            if diff
            else f"Good for one use, within {VALID_FOR_MINUTES} minutes of {now}.",
        ])
        return self._record_and_send(act.record, text)

    def report(self, record: str, state: str, summary: str, recommend: str | None) -> str:
        text = report_text(record, state, summary, recommend)
        return self._record_and_send(record, f"[report {stamp(self.clock)}] {text}")


def order(to: str, record: str, goal: str, limits: str, proof: str) -> str:
    given = {"to": to, "record": record, "goal": goal, "limits": limits, "proof": proof}
    fields.require(given, "orch send --order")
    fields.no_placeholder(given, "orch send --order")
    return "\n".join([
        f"Order to {to} on {record}.",
        f"Goal: {goal}",
        f"Limits: {limits}",
        f"Expected proof: {proof}",
    ])


def order_step(to: str) -> str:
    return (
        f"printed, not sent: orch send delivers nothing. Send the order below to {to} "
        "with SendMessage, or with your client's message tool."
    )


def send_step(record: str) -> str:
    return (
        f"next: this report is recorded on {record} only; orch report sends no message. "
        "Send the same text to the orchestrator session with SendMessage, "
        "or with your client's message tool."
    )


def report_text(record: str, state: str, summary: str, recommend: str | None) -> str:
    fields.require({"record": record, "summary": summary}, "orch report")
    if state not in REPORT_STATES:
        raise RefusedError(
            f"orch report refuses state {state!r}; use one of: {', '.join(REPORT_STATES)}"
        )
    if state == "needs-decision":
        fields.require({"recommend": recommend}, "orch report --state needs-decision")
    lines = [f"Report on {record}: {state}.", summary]
    if recommend:
        lines.append(f"Recommended: {recommend}")
    return "\n".join(lines)
