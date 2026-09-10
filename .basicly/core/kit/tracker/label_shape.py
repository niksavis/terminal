"""What a record's ``labels`` field holds, and how a reader gets the labels back out.

The boundary is the **shape**, against `commands.py`, which decides what a write does to the
set. Two shapes reach the fold and both are legitimate: a ``created`` event carries the list
an import extracted, and a `field` event cannot, because ``value`` is one of
`events.TRUNCATABLE_KEYS` and the schema refuses a container under a capped key.

**A bare string iterates as its characters, and naming that is why this module exists.**
``"phase-2"`` read with a ``for`` yields ``p, h, a, s, e, -, 2``; written back it is seven
labels of one character, and ``loop supervise --label phase-2`` then selects nothing. The
class is otherwise silent — every downstream reader sees well-formed strings — so the split
is declared once here and :func:`split_labels` lets `fsck` report a log that carries one.

It was a probe and not a writer that first produced that histogram (basicly-0cpn51): a script
iterated the string shape and reported 44 corrupted labels - the character census of four
`sess-0822` records - where the log held none. An analysis tripping this way argues for a gate.
"""

# comment-density-waiver: cohesion: 60.5% because the module is one rule and the meaning of
# one rule. `len(label) <= 1` recovers none of it: not that the two storage shapes are both
# legitimate, not that iterating the string shape is what produces the class, and not that
# the histogram this was filed from came from a probe rather than from a writer. The
# distinguishing evidence — 284 label-carrying events, shortest label three characters — is a
# measurement a reader cannot retake from the source. Same shape as `labels.py` beside it.

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    """Load a sibling kit module by path, `fsck._load`'s way and for its reason.

    Raises:
        ImportError: *file_name* is not beside this file.
    """
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside label_shape.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


events = _load("events.py", "basicly_tracker_kit_events")

# The field a record's labels live under, and the separator the joined form uses. Moved from
# `commands.py` rather than copied: split and write must agree about the separator, and a
# second copy of that answer is how two readers of one log read different populations
# (basicly-oii83r).
LABELS_FIELD = "labels"
LABEL_SEPARATOR = ","

# The two kinds that set the field, each in its own shape. From `events.py`, so a rename
# there fails loudly here.
KIND_CREATED = events.KIND_CREATED
KIND_FIELD = events.KIND_FIELD

# The character-iteration signature, never a label somebody chose: the shortest label across
# this repository's own 284 label-carrying events is `kit` at three. A length rather than a
# character set, so the `2` split out of `phase-2` is caught by the same rule as the `p`.
MAX_SPLIT_LABEL_CHARS = 1


def labels_of(value: object) -> tuple:
    """A folded ``labels`` field as the labels it names, whichever shape holds it.

    Args:
        value: The field as the fold holds it: a string, a list, or absent.

    Returns:
        Each non-empty label, in storage order. Empty for a field nothing set.
    """
    if isinstance(value, str):
        return tuple(part for part in (raw.strip() for raw in value.split(LABEL_SEPARATOR)) if part)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def labels_written_by(event: Any) -> tuple:
    """The labels *event* sets, or empty for an event that sets none.

    The payload the writer produced, not the fold: the fold keeps only the winning value, so
    a split write corrected by a later one is invisible there and is what a checker wants.

    Args:
        event: One appended event.

    Returns:
        Each label the payload names, split out of whichever shape carries it.
    """
    payload = event.payload
    if not isinstance(payload, dict):
        return ()
    if event.kind == KIND_CREATED:
        return labels_of(payload.get(LABELS_FIELD))
    if event.kind == KIND_FIELD and payload.get("name") == LABELS_FIELD:
        return labels_of(payload.get("value"))
    return ()


def split_labels(ordered: Any) -> tuple:
    """Every record in *ordered* whose label writes name a label of one character.

    Args:
        ordered: The events, in canonical order.

    Returns:
        ``(record, labels, event_ids)`` per affected record, every level sorted so two runs
        over one log report identically. Empty for a clean log.
    """
    found: dict = {}
    for event in ordered:
        offending = {
            label for label in labels_written_by(event) if len(label) <= MAX_SPLIT_LABEL_CHARS
        }
        if offending:
            labels, ids = found.setdefault(event.record, (set(), set()))
            labels |= offending
            ids.add(event.id)
    return tuple(
        (record, tuple(sorted(labels)), tuple(sorted(ids)))
        for record, (labels, ids) in sorted(found.items())
    )
