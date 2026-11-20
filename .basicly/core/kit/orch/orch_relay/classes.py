from __future__ import annotations

from orch_lessons.log import RefusedError

ASK_FIRST = "ask-first"
PERSON_APPROVES = "person-approves"
PERSON_WINDOW = "person-window"
COUNCIL_DECIDES = "council-decides"

ITEMS: dict[str, str] = {
    "ci-edit": ASK_FIRST,
    "deployment-edit": ASK_FIRST,
    "ignore-edit": ASK_FIRST,
    "secrets-file-edit": ASK_FIRST,
    "env-file": ASK_FIRST,
    "dependency": ASK_FIRST,
    "network-call": ASK_FIRST,
    "cleanup-delete": ASK_FIRST,
    "push": ASK_FIRST,
    "tag": ASK_FIRST,
    "release": ASK_FIRST,
    "docs-deploy": ASK_FIRST,
    "deploy": PERSON_APPROVES,
    "reversible-delete": PERSON_APPROVES,
    "permission-prompt": PERSON_WINDOW,
    "classifier-refusal": PERSON_WINDOW,
    "test-weakening": COUNCIL_DECIDES,
    "gate-weakening": COUNCIL_DECIDES,
    "hook-weakening": COUNCIL_DECIDES,
    "gate-exception": COUNCIL_DECIDES,
    "gate-bypass": COUNCIL_DECIDES,
    "hook-bypass": COUNCIL_DECIDES,
    "irreversible-destruction": PERSON_WINDOW,
    "private-data-exposure": PERSON_WINDOW,
    "rule-change": PERSON_APPROVES,
}

ROUTE = {
    ASK_FIRST: "an ask-first item; the orchestrator decides it with orch decide",
    PERSON_APPROVES: (
        "an item the person approves in the orchestrator window; relay it with orch approve"
    ),
    COUNCIL_DECIDES: (
        "a test, gate or hook change; the orchestrator decides it with orch decide --council"
    ),
    PERSON_WINDOW: (
        "an item that stays with the person in the worker's own window; "
        "no approval or decision covers it"
    ),
}


def item_class(item: str) -> str:
    if item not in ITEMS:
        known = ", ".join(sorted(ITEMS))
        raise RefusedError(f"unknown item {item!r}; name one of: {known}")
    return ITEMS[item]


def require_class(item: str, wanted: str | frozenset[str], command: str) -> None:
    found = item_class(item)
    if found not in ({wanted} if isinstance(wanted, str) else wanted):
        raise RefusedError(f"{command} refuses {item!r}: it is {ROUTE[found]}")
