r"""The owned ranking: a pure score over the graph, with no age term (basicly-vkh0.20).

§9.2 in `SPEC.md` settled this ranking, and the sharp half of it is a
*subtraction*: **the ranking must drop `created_at`**. An age term makes dispatch order
clock-dependent for a graph nobody changed — which D9 forbids for anything outliving the
pass. Two ledgers holding the same work, stamped by two clocks, must rank identically, and
the way that is won here is by **structure rather than by discipline**: :class:`Candidate`
is the whole input, it is built from `differential.RecordView` plus one integer, and
neither carries a timestamp. There is no clock argument to pass and no field to read, so an
age term cannot be reintroduced without changing the type.

That matters more than it sounds, because the ledger *does* hold the age. An imported
record's ``created`` event carries the source's ``created_at`` verbatim (`migrate.py`
imports every non-structural field), so a scorer taking the fold would have had it in
reach. Taking the view instead is what keeps it out.

## The ordering, and why each term is where it is

``priority ASC, dependents DESC, id ASC`` — §9.2's ordering, over the ready set only:

1. **Unblocked only.** `differential.is_ready` decides it, unchanged and not re-spelled
   here: dispatchable status, every blocking dependency closed, no parent-child children,
   never a tombstone. One definition of ready in the kit, which is the point of calling it.
2. **Priority**, ascending — 0 is critical, 4 is backlog, and 2 is what a record with no
   usable priority is read as.
3. **Dependent count**, descending: unblock the most work first, which is the critical
   path. Counted over :attr:`Vocabulary.blocking_types` edges only, and only from
   dependents that are still live — a closed or tombstoned dependent is work already done,
   and counting it would credit a record for releasing nothing. The type filter is not
   inert: this repo's own export holds 52 ``related`` and 1 ``discovered-from`` edge
   alongside 204 ``blocks``, and a ``related`` dependent is not waiting on anything.
   (Incoming ``parent-child`` edges cannot reach a ranked record at all — a record with a
   parent-child dependent has children, which `is_ready` refuses — so excluding them
   changes nothing today and keeps "dependent" meaning "unblocked by this".)
4. **Id**, ascending, as the final tie-break, so the order is total.

## The score is the ordering, and it decodes

A rank is evidence only if the number behind it can be re-read later (basicly-vkh0.3), so
the ranking is **by score, then id** rather than by a tuple the score merely accompanies:

    score = (BOTTOM_PRIORITY - priority) * PRIORITY_WEIGHT + min(dependents, DEPENDENT_CEILING)

Higher is better. Because :data:`PRIORITY_WEIGHT` is one more than
:data:`DEPENDENT_CEILING`, priority strictly dominates — no number of dependents lifts a P2
over a P1 — and the two terms stay separable: ``divmod(score, PRIORITY_WEIGHT)`` returns
them both, which is what :func:`explain` does. A recorded score plus :data:`SCHEMA` is
therefore self-describing without the graph that produced it.

The ceiling is what buys the domination, and it is a real (if distant) bound: at
:data:`DEPENDENT_CEILING` dependents the critical-path term saturates and two such records
tie, falling to id. Measured against this repo's live export — 643 records — the largest
blocking-dependent count is 5, so the ceiling is some two hundred times the observed
maximum. A priority *outside* the 0-4 band is not clamped: it scores negative or above the
band and still orders correctly, because clamping is the one treatment that would make two
different priorities tie.

## Every ready record is ranked

``in_progress`` included, because `is_ready` admits it and a second, narrower notion of
ready living here is the drift the kit exists to avoid (§9.2).

Nothing here reads a clock, spawns a process, or imports the engine (§4).
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


class SchedulerError(Exception):
    """The ranking was asked for something it cannot answer."""


# --- the sibling this is derived from -----------------------------------------

_HERE = Path(__file__).resolve().parent
_DIFFERENTIAL_MODULE_NAME = "basicly_tracker_kit_differential"


def _load_differential() -> ModuleType:
    """Load ``differential.py`` from beside this file, without touching ``sys.path``.

    The same by-path load every kit module uses for its siblings, under the same fixed
    ``sys.modules`` name they all follow (``basicly_tracker_kit_<module>``). The fixed name
    is the mechanism, not a convention: two loads of one file give two ``RecordView``
    classes, and a candidate built against one is not the type the other's ``is_ready``
    reads. The engine loads the differential under this exact name too (`basicly.br.kit`),
    so a host that has already loaded it hands the same module here.

    The differential rather than `events.py` directly, because it owns everything this
    module reads about the graph — the record view, the edge, the ready rule and the
    vocabulary that names the edge types — and a second spelling of any of them here is the
    drift the kit's loaders exist to prevent.
    """
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


# --- the policy, versioned so a recorded score stays readable -----------------

# The envelope a recorded rank is interpretable against (basicly-vkh0.3). Versioned because
# a bare integer means nothing without the policy that produced it, so a marker written
# under an older policy stays distinguishable on sight.
SCHEMA = "basicly.scheduler.v1"

# The ordering, in full, as the answer carries it. Not "the fallback sort": there is no
# evidence-weighted pass sitting above it that this could fall back *from* — this ordering
# is the ranking, which is why :class:`RankedRecord` has no separate fallback rank.
SORT = "priority ASC, dependents DESC, id ASC"

# Where the two ranking terms are read from on the fold, and the display field carried with
# them. Both `cli.py`'s ``create`` and `migrate.py` write them onto the ``created`` event.
PRIORITY_FIELD = "priority"
TITLE_FIELD = "title"

# The priority band and its default: 0 is critical, 4 is backlog, an omitted priority is 2.
# A record whose priority is absent or not an integer reads as the
# default rather than being refused — the ledger holds whatever was imported, and a ranking
# that raised on one malformed field would take the whole ready set down with it.
BOTTOM_PRIORITY = 4
DEFAULT_PRIORITY = 2

# Where the critical-path term saturates, and the scale that keeps priority above it. See
# the module docstring: the ceiling is ~200x this repo's observed maximum, and
# ``PRIORITY_WEIGHT = DEPENDENT_CEILING + 1`` is what makes ``divmod`` recover both terms.
DEPENDENT_CEILING = 999
PRIORITY_WEIGHT = DEPENDENT_CEILING + 1


# --- what the ranking reads ---------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """One record as the ranking sees it: the graph view, plus priority.

    Deliberately this narrow, and the narrowness *is* the age-freedom property — see the
    module docstring. :attr:`title` is carried for a caller that has to display the answer
    and is never a ranking term; it is the one field here the score does not read.

    Attributes:
        view: The record's `differential.RecordView` — status, edges and tombstone, which
            is everything :func:`differential.is_ready` needs and no timestamp.
        priority: The 0-4 band, :data:`DEFAULT_PRIORITY` when the ledger has no usable one.
        title: The record's title, for display only.
    """

    view: Any
    priority: int = DEFAULT_PRIORITY
    title: str = ""

    @property
    def record(self) -> str:
        """The record's id, taken from the view so the two cannot disagree."""
        return str(self.view.record)


@dataclass(frozen=True)
class RankedRecord:
    """One ranked record: its place and the score that put it there.

    The terms behind the score are **not** carried, and that is the design rather than an
    omission: the score encodes them (:func:`explain`), so duplicating them here would give
    a reader two sources for one fact and give the marker two things to record. What is
    recorded on a dispatch is the score and :data:`SCHEMA`, and those two are sufficient.

    Attributes:
        rank: 1-based position in the answer.
        score: :func:`score`'s value — the ordering, not a commentary on it.
        record: The record's id.
        title: Its title, for display.
    """

    rank: int
    score: int
    record: str
    title: str = ""


@dataclass(frozen=True)
class Ranking:
    """The ready set in order, with the policy that produced it.

    The envelope travels with the answer for the reason vkh0.3 gave: a rank recorded
    without its policy is uninterpretable later, and the flip means two policies now exist
    in recorded history.

    Attributes:
        records: The ranked ready set, best first.
        schema: :data:`SCHEMA`.
        sort: :data:`SORT`.
    """

    records: tuple[RankedRecord, ...] = ()
    schema: str = SCHEMA
    sort: str = SORT


@dataclass(frozen=True)
class ScoreTerms:
    """A score decoded back into the two terms that built it.

    Attributes:
        priority: The priority band.
        dependents: The saturated critical-path term.
    """

    priority: int
    dependents: int


# --- the pure ranking ---------------------------------------------------------


def score(priority: int, dependents: int) -> int:
    """The record's score: priority dominant, dependents beneath it, higher is better.

    Args:
        priority: The 0-4 band. Outside it the score leaves the band rather than clamping,
            which keeps two different priorities from tying.
        dependents: Live blocking dependents, saturating at :data:`DEPENDENT_CEILING`.
    """
    return (BOTTOM_PRIORITY - priority) * PRIORITY_WEIGHT + min(dependents, DEPENDENT_CEILING)


def explain(value: int) -> ScoreTerms:
    """Decode a recorded *value* back into its terms, exactly inverting :func:`score`.

    What makes a score evidence rather than an opinion: a marker recorded months ago
    carries an integer and :data:`SCHEMA`, and this turns that pair back into "P1, three
    dependents" without the graph it was computed over. Exact for a saturated dependent
    count only up to the ceiling, which is what saturation means.
    """
    band, dependents = divmod(value, PRIORITY_WEIGHT)
    return ScoreTerms(priority=BOTTOM_PRIORITY - band, dependents=dependents)


def dependents_of(views: Mapping[str, Any], vocabulary: Any) -> dict[str, int]:
    """How much live work each record is blocking, keyed by record id.

    Counted from the dependents' own outgoing edges, because that is the side both stores
    hold one on (`differential.Edge`). Two filters, each doing real work on this repo's
    graph: only :attr:`Vocabulary.blocking_types` edges count, and a dependent that is
    itself closed or tombstoned counts for nothing — it is work already done, and crediting
    a record for releasing it would rank a finished branch of the graph above a live one.
    """
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
    """Rank the ready records in *candidates* by :data:`SORT`.

    A pure function of the graph: the same candidates rank identically however much time
    has passed and whatever clock wrote the ledger they came out of.

    Args:
        candidates: Every record the ledger holds, keyed by id. The whole population rather
            than a pre-filtered ready set, because readiness and the dependent count are
            both properties of the *graph* — a blocker left out reads as unknown, and
            `is_ready` refuses an unknown blocker rather than assuming it satisfied.
        vocabulary: The engine's names for statuses and edge types.
            `differential.DEFAULT_VOCABULARY` when omitted.
        limit: Keep only the top *limit* records.

    Raises:
        SchedulerError: *limit* is negative — refused rather than silently truncating from
            the wrong end, which is what a negative slice would do.
    """
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
    # Highest score first, then id ascending — the last term of :data:`SORT`, and what
    # makes the order total rather than whatever the population's iteration order was.
    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    ordered = scored if limit is None else scored[:limit]
    return Ranking(
        records=tuple(
            RankedRecord(rank=position, score=value, record=record, title=title)
            for position, (value, record, title) in enumerate(ordered, start=1)
        )
    )


# --- reading the ledger -------------------------------------------------------


def _priority(fields: Mapping[str, object]) -> int:
    """The record's priority band, or :data:`DEFAULT_PRIORITY` when it has no usable one.

    ``bool`` is refused despite being an ``int``: ``True`` would silently rank as P1.
    """
    value = fields.get(PRIORITY_FIELD)
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_PRIORITY
    return value


def candidates_from_events(ledger_events: Iterable[Any]) -> dict[str, Candidate]:
    """Every record in *ledger_events* as a :class:`Candidate`.

    Two passes over one event list, and the second is not redundancy — it is the same split
    `basicly.br.owned_record` makes: `differential.views_from_events` is the only reader of
    the ``edge`` kind, which `events.fold` has no handler for, while the fold is the
    authority for the record fields the view deliberately leaves out. Priority is one of
    those fields, so both are needed.
    """
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
    """The ranked ready set of the ledger at *directory*.

    The convenience half — reads the ledger, builds the candidates, ranks them — kept
    separate from :func:`rank` so the ordering can be exercised without a filesystem.
    """
    return rank(
        candidates_from_events(differential.read_ledger(directory)),
        vocabulary=vocabulary,
        limit=limit,
    )
