from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DifferentialError(Exception):
    pass


QUERY_PHASE = "phase"
QUERY_READY = "ready"
QUERY_GATES = "gates"
QUERIES = (QUERY_PHASE, QUERY_READY, QUERY_GATES)


@dataclass(frozen=True)
class GateRow:
    gate: str
    provider: str
    passed: bool


@dataclass(frozen=True)
class Edge:
    target: str
    type: str


@dataclass(frozen=True)
class RecordView:
    record: str
    status: str = ""
    external_ref: str = ""
    comments: tuple[str, ...] = ()
    dependencies: tuple[Edge, ...] = ()
    gates: tuple[GateRow, ...] = ()
    tombstoned: bool = False


@dataclass(frozen=True)
class GateVerdict:
    passed: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    advisory: tuple[GateRow, ...] = ()
    disregarded: tuple[GateRow, ...] = ()
    can_advance: bool = False


@dataclass(frozen=True)
class Verdict:
    phase: str
    ready: bool
    gates: GateVerdict

    def answer(self, query: str) -> Any:

        if query == QUERY_PHASE:
            return self.phase
        if query == QUERY_READY:
            return self.ready
        if query == QUERY_GATES:
            return self.gates
        raise DifferentialError(f"unknown query {query!r}; expected one of {', '.join(QUERIES)}")
