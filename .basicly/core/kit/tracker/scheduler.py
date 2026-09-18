from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


class SchedulerError(Exception):
    pass


_HERE = Path(__file__).resolve().parent
_DIFFERENTIAL_MODULE_NAME = "basicly_tracker_kit_differential"


def _load_differential() -> ModuleType:

    cached = sys.modules.get(_DIFFERENTIAL_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        _DIFFERENTIAL_MODULE_NAME, _HERE / "differential.py"
    )
    if spec is None or spec.loader is None:
        raise SchedulerError(
            "the tracker kit's differential.py is missing from beside scheduler.py"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_DIFFERENTIAL_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


differential = _load_differential()
events = differential.events


SCHEMA = "basicly.scheduler.v1"

SORT = "priority ASC, dependents DESC, id ASC"

PRIORITY_FIELD = "priority"
TITLE_FIELD = "title"

BOTTOM_PRIORITY = 4
DEFAULT_PRIORITY = 2

DEPENDENT_CEILING = 999
PRIORITY_WEIGHT = DEPENDENT_CEILING + 1


@dataclass(frozen=True)
class Candidate:
    view: Any
    priority: int = DEFAULT_PRIORITY
    title: str = ""

    @property
    def record(self) -> str:
        return str(self.view.record)


@dataclass(frozen=True)
class RankedRecord:
    rank: int
    score: int
    record: str
    title: str = ""


@dataclass(frozen=True)
class Ranking:
    records: tuple[RankedRecord, ...] = ()
    schema: str = SCHEMA
    sort: str = SORT


@dataclass(frozen=True)
class ScoreTerms:
    priority: int
    dependents: int


def score(priority: int, dependents: int) -> int:

    return (BOTTOM_PRIORITY - priority) * PRIORITY_WEIGHT + min(dependents, DEPENDENT_CEILING)


def explain(value: int) -> ScoreTerms:

    band, dependents = divmod(value, PRIORITY_WEIGHT)
    return ScoreTerms(priority=BOTTOM_PRIORITY - band, dependents=dependents)


def dependents_of(views: Mapping[str, Any], vocabulary: Any) -> dict[str, int]:

    counts: dict[str, int] = {}
    for record in sorted(views):
        view = views[record]
        if view.tombstoned or view.status in vocabulary.closed_statuses:
            continue
        for edge in view.dependencies:
            if edge.type in vocabulary.blocking_types:
                counts[edge.target] = counts.get(edge.target, 0) + 1
    return counts


def rank(
    candidates: Mapping[str, Candidate],
    *,
    vocabulary: Any = None,
    limit: int | None = None,
) -> Ranking:

    if limit is not None and limit < 0:
        raise SchedulerError(f"limit must not be negative, got {limit}")
    vocabulary = differential.DEFAULT_VOCABULARY if vocabulary is None else vocabulary
    views = {record: candidate.view for record, candidate in candidates.items()}
    children = differential.children_of(views, vocabulary)
    dependents = dependents_of(views, vocabulary)
    scored = [
        (score(candidate.priority, dependents.get(record, 0)), record, candidate.title)
        for record, candidate in candidates.items()
        if differential.is_ready(candidate.view, views, children, vocabulary)
    ]
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    ordered = scored if limit is None else scored[:limit]
    return Ranking(
        records=tuple(
            RankedRecord(rank=position, score=value, record=record, title=title)
            for position, (value, record, title) in enumerate(ordered, start=1)
        )
    )


def _priority(fields: Mapping[str, object]) -> int:

    value = fields.get(PRIORITY_FIELD)
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_PRIORITY
    return value


def candidates_from_events(ledger_events: Iterable[Any]) -> dict[str, Candidate]:

    collected = list(ledger_events)
    views = differential.views_from_events(collected)
    folded = events.fold(collected)
    candidates: dict[str, Candidate] = {}
    for record, view in views.items():
        fields = folded.records[record].fields
        title = fields.get(TITLE_FIELD)
        candidates[record] = Candidate(
            view=view,
            priority=_priority(fields),
            title=title if isinstance(title, str) else "",
        )
    return candidates


def ranking(directory: Path | str, *, limit: int | None = None, vocabulary: Any = None) -> Ranking:

    return rank(
        candidates_from_events(differential.read_ledger(directory)),
        vocabulary=vocabulary,
        limit=limit,
    )
