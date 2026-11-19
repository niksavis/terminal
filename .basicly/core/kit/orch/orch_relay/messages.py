from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orch_lessons.log import Clock, RefusedError, check_text, utc_now

from orch_relay import classes, fields

if TYPE_CHECKING:
    from orch_relay.record import Tracker

VALID_FOR_MINUTES = 60
REPORT_STATES = ("done", "blocked", "needs-decision")
RULE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

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


def _action_lines(act: Action, parsed: list[fields.Risk]) -> list[str]:
    return [
        f"Record: {act.record}",
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


@dataclass(frozen=True)
class Writer:
    tracker: Tracker
    scan: Scan
    clock: Clock = utc_now

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
        if not RULE_DATE.fullmatch(rule_date.strip()):
            raise RefusedError("orch decide refuses --rule-date: write it as YYYY-MM-DD")
        classes.require_class(act.item, classes.ASK_FIRST, "orch decide")
        fields.no_placeholder(given, "orch decide")
        parsed = fields.risks(act.risks, act.action)
        now = stamp(self.clock)
        text = "\n".join([
            f"[decision {now}] Orchestrator decision on an ask-first item.",
            f'Rule that lets the orchestrator decide ask-first items ({rule_date}): "{rule}"',
            f"Entry stamp: {now}",
            *_action_lines(act, parsed),
            f"Reason: {reason}",
            f"Condition: {condition}",
            f"Proof command: {proof}",
            f"If the proof fails: {if_proof_fails}",
            f"Good for one use, within {VALID_FOR_MINUTES} minutes of {now}.",
        ])
        return self._record_and_send(act.record, text)

    def approve(self, act: Action, words: str) -> str:
        given = {
            "item": act.item,
            "record": act.record,
            "repo": act.repo,
            "action": act.action,
            "words": words,
        }
        fields.require(given, "orch approve")
        classes.require_class(act.item, classes.PERSON_APPROVES, "orch approve")
        fields.no_placeholder({k: v for k, v in given.items() if k != "words"}, "orch approve")
        parsed = fields.risks(act.risks, act.action)
        now = stamp(self.clock)
        text = "\n".join([
            f"[approval {now}] The person's approval, relayed by the orchestrator.",
            f'The person\'s words at {now}: "{words}"',
            *_action_lines(act, parsed),
            f"Good for one use, within {VALID_FOR_MINUTES} minutes of {now}.",
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
