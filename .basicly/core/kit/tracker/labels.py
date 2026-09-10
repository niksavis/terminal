"""What a provenance label means, what it permits, and the names an edge payload uses.

The boundary is the **vocabulary**, against :mod:`provenance`, which writes an edge, reads
one back and folds them. Split out when `provenance.py` sat at 7,890 tokens - exactly its
frozen baseline, so the vocabulary could not gain the entry `basicly-493g5f` needs.

Two callers read this rather than one, and that is the point. `provenance.py` folds edges and
`differential.py` folds record views, and both need the same answer to *which spelling is this
payload in*. A second copy of that table is exactly how the two came to read different
populations of one log (basicly-oii83r), so it is declared once, here.

**The key is shared with a second vocabulary and that is a collision, not a design.**
`migrate.PROVENANCE_KEY` and :data:`KEY_LABEL` are the same string. This module reads it as
*how strong the evidence is*; the engine's write seam stamps it with *who wrote the event*.
:data:`WRITER_LABELS` is what makes the second axis legible instead of unknown.
"""

# comment-density-waiver: cohesion: 74.7% because the module is a vocabulary - three
# evidence labels, two writer identities, two dialect spellings, four payload key names -
# and what each one
# *means* is the payload. A label here is a string that crosses a JSON boundary into a
# consumer's ledger and decides whether an edge may gate a landing, so the rule it carries
# cannot be recovered from `EXTRACTED = "EXTRACTED"`. Third instance in one pass of the two
# ratchets pulling opposite ways on a split the size ratchet demanded (basicly-e2r08j).

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

# --- the sibling event log ----------------------------------------------------

_HERE = Path(__file__).resolve().parent
EVENTS_MODULE_NAME = "basicly_tracker_kit_events"


def _load_events() -> Any:
    """Load ``events.py`` from beside this file, without touching ``sys.path``.

    The same loader `events.py` uses for `ids.py`, for the same reason: the kit is a set
    of sibling files rather than a package, and this is a library inside somebody else's
    process, so ``events`` is a name they may well own. The module name is **public**
    because it is a contract with the caller — a caller loading `events.py` under a
    second name would get a second copy of :class:`events.InvalidEventError`, and
    ``except`` clauses on it would stop matching. Load it from here, or load it under
    this name.

    Returns:
        The loaded module. Typed as :data:`~typing.Any` rather than ``object`` — unlike
        `events.py`'s loader — because this module subclasses one of its exceptions, and
        a base class cannot come from an ``object``-typed name.

    Raises:
        ImportError: ``events.py`` is not beside this file.
    """
    cached = sys.modules.get(EVENTS_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(EVENTS_MODULE_NAME, _HERE / "events.py")
    if spec is None or spec.loader is None:
        raise ImportError("the tracker kit's events.py is missing from beside provenance.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[EVENTS_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


events = _load_events()


class InvalidEdgeError(events.InvalidEventError):
    """An edge assertion that cannot be recorded, or a recorded one that cannot be read.

    A subclass of the event log's own :class:`events.InvalidEventError`, so a caller
    wrapping a build-and-append in one ``except events.LedgerError`` catches both halves
    rather than the draft builder's refusal escaping the handler written for the write.
    """


# --- the vocabulary -----------------------------------------------------------

EXTRACTED = "EXTRACTED"
INFERRED = "INFERRED"
AMBIGUOUS = "AMBIGUOUS"

# Order matters only for a stable report; :data:`_STRENGTH` is what ranks them.
LABELS = (AMBIGUOUS, EXTRACTED, INFERRED)

# The engine's own writer identities, which land in this key by **collision rather than by
# design**: `migrate.PROVENANCE_KEY` and :data:`KEY_LABEL` are the same string, so the write
# seam stamps *who wrote the event* into the field this module reads as *how strong the
# evidence is*. Two axes, one name.
#
# Measured on this repository's log 2026-08-20: 142 of the edge events carry one of these -
# `engine` 70, `dual-write` 72 - folding to 133 edges that were disposed `decide` for want of
# a vocabulary rather than for want of a fact, which is why `gating_edges` read 932 of 1065.
#
# They rank and dispose as :data:`EXTRACTED` because of *what they mean*, not as a
# convenience: an event the engine's write seam appended is one a command asked for, which is
# the same claim `EXTRACTED` makes. This widens the gating set by two **exact** strings and
# keeps the rule that only an exact known string gates - it is not a prefix or a fallback.
# Counted separately in :attr:`EdgeFold.writer_labels`, because an edge that carried a writer
# identity never carried an evidence label and a report that merged the two would say it did.
#
# Pinned against the engine's own constants by `tests/test_kit_tracker_provenance.py`, so a
# rename in `owned_write` or `mirror` fails loudly instead of silently reopening the blindness
# (basicly-493g5f).
WRITER_LABELS = frozenset({"engine", "dual-write"})

# How much a label is worth when two events disagree. Not exposed as a number: a caller
# comparing strengths is asking about a disposition, and :func:`disposition` answers that
# without inviting a fourth label to be slotted between two existing ones by arithmetic.
_STRENGTH = {AMBIGUOUS: 1, INFERRED: 2, EXTRACTED: 3} | dict.fromkeys(WRITER_LABELS, 3)

# A label from a newer writer ranks below every label we know, so it can never win a
# promotion contest and can never inherit a stronger label's disposition.
_UNKNOWN_STRENGTH = 0

# What an edge is allowed to do, one per label. Strings rather than an enum: the kit
# targets an interpreter older than this repo's and these values cross a JSON boundary
# into the engine's decision queue, where a string is what arrives anyway.
DISPOSITION_GATE = "gate"
DISPOSITION_PROPOSE = "propose"
DISPOSITION_DECIDE = "decide"

_DISPOSITIONS = {
    EXTRACTED: DISPOSITION_GATE,
    INFERRED: DISPOSITION_PROPOSE,
    AMBIGUOUS: DISPOSITION_DECIDE,
} | dict.fromkeys(WRITER_LABELS, DISPOSITION_GATE)

# The kind an edge assertion is recorded under, from the one definition (§4.5).
KIND_EDGE = events.KIND_EDGE

# The payload's structural fields. `detail` is the only free-text one, and the only one
# `events.TRUNCATABLE_KEYS` may cut — see the module docstring for why that split is not
# a style choice.
#
# One spelling per field on the **write** side, and these names are it (R2). A store spelling
# one dependency edge `id`/`dependency_type` from one command and `depends_on_id`/`type` from
# another leaves a reader of the wrong spelling with an empty graph rather than an error
# (basicly-kjc5.10) — which is what this module then did to itself, per the block below.
KEY_TARGET = "target"
KEY_TYPE = "edge_type"
KEY_LABEL = "provenance"
KEY_DETAIL = "detail"

# The **read** side takes a second dialect, because the log already holds one. `migrate.py`
# writes `to`/`type` and `differential.py` reads it, so all 1,083 edge events committed here
# are in that spelling and none is in the pair above [measured 2026-08-20]; the split is
# recorded in `fsck.py`. This fold therefore read *zero* of them and `gating_edges` answered
# for the whole population by seeing nothing — a fail-open, and the reason the second name of
# each pair is accepted on read and never written (basicly-svct4w). The equality with
# `migrate.py`'s own constants is pinned by a test, so a rename there fails loudly instead of
# silently reopening the blindness.
ALT_KEY_TARGET = "to"
ALT_KEY_TYPE = "type"

# What :attr:`EdgeFold.dialects` counts under. The fold **says which spelling it read**: an
# empty edge set is otherwise the same answer for a ledger with no edges and a ledger whose
# every edge the reader could not parse, and those are opposite facts.
DIALECT_DECLARED = f"{KEY_TARGET}/{KEY_TYPE}"
DIALECT_ENGINE = f"{ALT_KEY_TARGET}/{ALT_KEY_TYPE}"

# Dialect to the two structural keys that spell it. Public because two folds read it -
# `provenance.read_assertion` and `differential.views_from_events` - and a second copy is
# how they came to read different populations of one log (basicly-oii83r).
DIALECT_KEYS = {
    DIALECT_DECLARED: (KEY_TARGET, KEY_TYPE),
    DIALECT_ENGINE: (ALT_KEY_TARGET, ALT_KEY_TYPE),
}

# The edge type is caller vocabulary — `blocks`, `parent-child`, `discovered-from` — but
# it is still a permanent token, so it is restricted to a shape every surface can round
# trip. A hyphen is fine here and only here: this is a payload value, never part of an id,
# so the commit gate's first-hyphen split (`ids.validate_prefix`) cannot reach it.
EDGE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# The decision queue's kind for an edge that cannot stand on its own. `validate` is the
# engine's existing entry for *an uncertain machine judgment a human should check*
# (`decisions.KINDS`), which is precisely §9.6's disposition for `AMBIGUOUS` — the point
# of routing there is that the path already exists and is already governed by D2.
DECISION_KIND = "validate"


def strength_of(label: str) -> int:
    """How strong *label* is, for the promotion contest. Unknown ranks below all of them.

    Args:
        label: The label to rank.

    Returns:
        A positive rank for a known label, ``0`` for anything else.
    """
    return _STRENGTH.get(label, _UNKNOWN_STRENGTH)


def disposition(label: str) -> str:
    """What an edge carrying *label* may do.

    Fails closed: a label this version does not know gets :data:`DISPOSITION_DECIDE`,
    never :data:`DISPOSITION_GATE`. Only the exact known string gates.

    Args:
        label: The label to dispose of.

    Returns:
        One of :data:`DISPOSITION_GATE`, :data:`DISPOSITION_PROPOSE` or
        :data:`DISPOSITION_DECIDE`.
    """
    return _DISPOSITIONS.get(label, DISPOSITION_DECIDE)


def validate_label(label: str) -> str:
    """Return *label* unchanged, or refuse it — on the **write side only**.

    The read side deliberately does not call this: a newer writer's label is preserved
    and disposed of conservatively rather than rejected (see the module docstring).

    Args:
        label: The label a caller is about to assert.

    Returns:
        *label*, unchanged.

    Raises:
        InvalidEdgeError: *label* is not one this version can assert.
    """
    if label not in LABELS:
        raise InvalidEdgeError(f"provenance label {label!r} must be one of {LABELS}")
    return label


def validate_edge_type(edge_type: str) -> str:
    """Return *edge_type* unchanged, or refuse it.

    Args:
        edge_type: The relation the edge names, read source-to-target.

    Returns:
        *edge_type*, unchanged.

    Raises:
        InvalidEdgeError: *edge_type* does not match :data:`EDGE_TYPE_PATTERN`.
    """
    if not EDGE_TYPE_PATTERN.match(edge_type):
        raise InvalidEdgeError(f"edge type {edge_type!r} must match {EDGE_TYPE_PATTERN.pattern}")
    return edge_type


def _has_text(payload: Any, key: str) -> bool:
    """Whether *key* clears the bar :func:`_required_text` sets, without raising."""
    value = payload.get(key)
    return isinstance(value, str) and bool(value)


def edge_dialect(payload: Any) -> str:
    """Which spelling *payload* carries both structural fields in.

    :data:`DIALECT_ENGINE` only when that pair is complete **and** this module's own is
    not, so a payload carrying both is read as the declared one and a payload carrying
    neither still reads as declared — which is what keeps the refusal in
    :func:`read_assertion` naming the documented spelling rather than guessing which of
    two writers meant to produce an unreadable line.

    Args:
        payload: The event's payload.

    Returns:
        :data:`DIALECT_DECLARED` or :data:`DIALECT_ENGINE`. Never empty: an unreadable
        payload is a refusal from the caller, not a third dialect.
    """
    declared = _has_text(payload, KEY_TARGET) and _has_text(payload, KEY_TYPE)
    engine = _has_text(payload, ALT_KEY_TARGET) and _has_text(payload, ALT_KEY_TYPE)
    return DIALECT_ENGINE if engine and not declared else DIALECT_DECLARED
