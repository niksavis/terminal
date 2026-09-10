"""Mint the work tracker's two kinds of id: opaque records, content-derived evidence.

The split this module exists to keep (§9.4 in `SPEC.md`, basicly-vkh0.12),
and it is a split rather than a preference because the two kinds have opposite
lifetimes:

- **A record is mutable.** Titles, descriptions and acceptance criteria are edited
  constantly, so an id derived from a record's content would either drift when the
  content changed or lie when it did not. A record id is therefore **opaque**: a short
  random root token plus a dotted monotonic child suffix, ``<prefix>-<root>.<n>``.
- **Evidence is immutable.** A decision, a found-info record, a dispatch marker is a
  fact about a moment. Those ids **are** derived from content, which is exactly what
  makes re-recording the same fact idempotent instead of duplicated.

Neither kind ever embeds caller text. Content reaches an id only through a hex digest,
and a prefix, a root and a family are each restricted to ``[a-z0-9]`` — see *No slugs*
below for the shipped defect that rule comes from.

## The declared collision budget

"Collision-checked" is a hand-wave: a mint can only check the ids *this* writer can
see, and two branches minting from the same base collide invisibly and merge into one
id. So the root length is sized from the birthday bound against a declared maximum
probability instead:

    P(collision) ≈ 1 - e^(-n² / 2N),   N = RADIX ** length

where *n* is the number of **distinct roots** under one prefix (not the number of
records — children share their root). The declared target is
:data:`MAX_COLLISION_PROBABILITY` = ``1e-4``, one chance in ten thousand that any pair
of all roots ever minted collides, and it yields:

| root length | id space N | max roots at P ≤ 1e-4 |
| --- | --- | --- |
| 4 | 1,679,616 | 18 |
| 5 | 60,466,176 | 109 |
| 6 | 2,176,782,336 | 659 |
| 7 | 78,364,164,096 | 3,958 |

That table is derived, not typed: :func:`max_population` recomputes every row and
``tests/test_kit_tracker_ids.py`` parses this docstring and asserts the two agree, so
the number a reader checks here cannot drift from the number a mint uses. The exact
birthday probability, ``1 - Π(1 - i/N)``, is *lower* than the approximation at every
row above, so the approximation is the conservative side to be on — also asserted.

Why 1e-4 rather than something tighter: a collision is not data loss (the local check
retries, and a cross-branch collision is a visible fork rather than a silent
overwrite), and ids are read and typed by people, so length is a real cost. For scale,
this repo's own ledger holds 311 roots across 636 records at 3-4 characters, measured
2026-08-06 — a 4-character root at that population carries P ≈ 2.8e-2, which is 284 times
the target this module declares. Sizing from a stated bound is what turns that from an
opinion into a check.

**Adaptive length is safe because an existing id never changes.** Only a newly minted
root gets longer; every id already handed out keeps the length it was minted at, and
:func:`mint_root_id` treats it as taken forever regardless. That is also why ids are
never reused: the caller passes every id ever minted — a deleted record's id included,
which is what a tombstone is for (:func:`minted_ever`) — and a candidate matching any
of them is discarded.

## No slugs, and the mechanism

An id like ``basicly-my-slug`` defeats the commit-message gate, which
derives its known prefixes by splitting an id at the *first* hyphen: it then reads that
id as prefix ``basicly`` plus root ``my``, finds ``basicly-my`` in no ledger, and
rejects the commit as referencing an unknown issue (basicly-jms0). A hyphen inside an
id is therefore not a style question, and this module makes it unrepresentable rather
than discouraged. The gate's own ``validate`` is called on minted ids in the tests,
including the positive control that a hyphenated id really is refused.

## What this module may not do

Kit rules (§4 in `SPEC.md`): **no basicly**, standard library only, no
network, no subprocess, no file or environment access — everything comes in as an
argument. It also reads **no clock**: §9.5 makes a timestamp evidence rather than a
constraint, and nothing here has a timestamp to be tempted by. Ordering of the child
suffix is a per-parent index, deliberately *not* the per-item event sequence number
that the event log assigns (§4.1); the two are different counters.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Collection, Iterable

# Base-36 lowercase, the alphabet the gate's `[a-z0-9]+` accepts and the one our own
# ledger already uses. Ambiguous characters are deliberately *not* removed: a smaller
# alphabet is a longer id for the same collision budget, and these ids are copied from
# a terminal rather than read aloud.
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
RADIX = len(ALPHABET)

PREFIX_SEP = "-"
CHILD_SEP = "."
EVIDENCE_SEP = "#"

# The declared budget of the docstring's table. One in ten thousand across every root
# ever minted under one prefix.
MAX_COLLISION_PROBABILITY = 1e-4

# Four is where our own ids start and is comfortable to type; twelve is not a cap on
# growth but the point where `IdSpaceExhaustedError` is raised rather than a longer id
# silently accepted (a 12-character root holds ~30 million roots at the declared
# target, so reaching it means something is wrong with the caller, not the ledger).
MIN_ROOT_LENGTH = 4
MAX_ROOT_LENGTH = 12

# Retries at one length before growing it. A collision here is a *local* one — the
# candidate is already in the taken set — so hitting sixteen in a row means the length
# is too short for the population rather than that the draw was unlucky.
MINT_ATTEMPTS = 16

# Digest characters kept in an evidence id: ten, matching `decisions.decision_id_for`
# and `run_record.marker_id`, which this module reproduces exactly.
DIGEST_CHARS = 10

_RECORD = r"[a-z][a-z0-9]*-[a-z0-9]+(?:\.[0-9]+)*"
_FAMILY = r"[a-z][a-z0-9]*"
_DIGEST = rf"[0-9a-f]{{{DIGEST_CHARS}}}"

# One rule, two names: a ledger prefix and an evidence family are both a visible token
# inside an id, so both must survive the gate's first-hyphen split (see *No slugs*).
PREFIX_PATTERN = re.compile(rf"^{_FAMILY}$")
FAMILY_PATTERN = re.compile(rf"^{_FAMILY}$")
RECORD_ID_PATTERN = re.compile(rf"^{_RECORD}$")
EVIDENCE_ID_PATTERN = re.compile(
    rf"^{_RECORD}{EVIDENCE_SEP}(?:(?:{_FAMILY}-)?{_DIGEST}(?:-[0-9]+)?|{_FAMILY})$"
)

# `str.isdigit` is true for '٣' and '²', which would parse to a child index that no
# ledger could round-trip. ASCII only, explicitly.
_INDEX_PATTERN = re.compile(r"^[0-9]+$")

# The default source of randomness. `SystemRandom` rather than the module-level
# `random`, so a root is never predictable from a seed the process shares with
# something else; a test injects a seeded `random.Random` in its place, which is why
# the parameter exists at all.
_SYSTEM_RANDOM = random.SystemRandom()


class IdError(ValueError):
    """A prefix, family, id or generation that cannot appear in a tracker id."""


class IdSpaceExhaustedError(IdError):
    """No id of an allowed length is free, so nothing is minted rather than reused."""


def collision_probability(population: int, length: int) -> float:
    """The birthday-bound collision probability for *population* roots of *length*.

    ``1 - e^(-n²/2N)`` with ``N = RADIX ** length``, written as ``-expm1(-x)`` because
    the interesting values of x are small enough that ``1 - exp(-x)`` loses most of its
    significant digits.
    """
    if population < 2:
        return 0.0
    n = float(population)
    return -math.expm1(-(n * n) / (2.0 * float(RADIX**length)))


def max_population(length: int, *, target: float = MAX_COLLISION_PROBABILITY) -> int:
    """The largest root population *length* characters carry within *target*.

    Seeded by inverting the bound (``n = sqrt(-2N·ln(1-P))``, as ``log1p(-target)``)
    and then corrected against :func:`collision_probability` itself, so a float
    rounding error at the boundary cannot make this disagree with the function that
    :func:`root_length_for` actually branches on.
    """
    if length < 1:
        raise IdError(f"root length must be at least 1, got {length}")
    if not 0.0 < target < 1.0:
        raise IdError(f"collision target must be inside (0, 1), got {target}")
    population = int(math.sqrt(-2.0 * float(RADIX**length) * math.log1p(-target)))
    while collision_probability(population + 1, length) <= target:
        population += 1
    while population > 0 and collision_probability(population, length) > target:
        population -= 1
    return population


def root_length_for(population: int, *, target: float = MAX_COLLISION_PROBABILITY) -> int:
    """The shortest root length holding *population* roots within *target*.

    *population* is the count the ledger will have **after** the mint in hand, so
    :func:`mint_root_id` passes ``len(roots) + 1``.
    """
    if population < 0:
        raise IdError(f"population cannot be negative, got {population}")
    for length in range(MIN_ROOT_LENGTH, MAX_ROOT_LENGTH + 1):
        if collision_probability(population, length) <= target:
            return length
    raise IdSpaceExhaustedError(
        f"{population} roots need more than {MAX_ROOT_LENGTH} characters "
        f"to stay within P(collision) <= {target}"
    )


def validate_prefix(prefix: str) -> str:
    """Return *prefix* unchanged, or raise :class:`IdError` naming what is wrong.

    A hyphen is called out separately because it is the shipped defect (basicly-jms0)
    rather than a generic charset miss, and a caller reaching for one is reaching for a
    slug.
    """
    if PREFIX_SEP in prefix:
        raise IdError(
            f"prefix {prefix!r} contains {PREFIX_SEP!r}: the commit-message gate reads "
            f"the first hyphen as the prefix boundary, so the id would be refused"
        )
    if not PREFIX_PATTERN.match(prefix):
        raise IdError(f"prefix {prefix!r} must match {PREFIX_PATTERN.pattern}")
    return prefix


def validate_record_id(record_id: str) -> str:
    """Return *record_id* unchanged, or raise :class:`IdError` if it is not one."""
    if not RECORD_ID_PATTERN.match(record_id):
        raise IdError(f"{record_id!r} is not a record id: expected {RECORD_ID_PATTERN.pattern}")
    return record_id


def is_record_id(value: str) -> bool:
    """True when *value* is a well-formed record id."""
    return bool(RECORD_ID_PATTERN.match(value))


def is_evidence_id(value: str) -> bool:
    """True when *value* is a well-formed evidence id."""
    return bool(EVIDENCE_ID_PATTERN.match(value))


def minted_ever(live: Iterable[str], tombstoned: Iterable[str] = ()) -> frozenset[str]:
    """The id space a mint must avoid: every id handed out, live or deleted.

    Naming the union is the point. A mint that checked only live ids would hand a
    deleted record's id to a new one, and the ledger's history would then read as one
    record that changed its mind — which is why a delete leaves a **tombstone** rather
    than removing anything (§9.4 in `SPEC.md`).
    """
    return frozenset(live) | frozenset(tombstoned)


def root_ids(minted: Iterable[str], prefix: str) -> frozenset[str]:
    """The distinct root tokens under *prefix* — the population the bound is sized on.

    Children share their parent's root, so a ledger of 600 records may hold 300 roots;
    counting records instead would over-length every id. Ids under another prefix
    cannot collide with ours and are ignored, and so is anything that is not a record id
    — an evidence id mixed into the set would otherwise count as a root of its own and
    inflate the population the budget is sized on.
    """
    head = f"{prefix}{PREFIX_SEP}"
    roots = set()
    for value in minted:
        if value.startswith(head) and RECORD_ID_PATTERN.match(value):
            roots.add(value[len(head) :].split(CHILD_SEP, 1)[0])
    return frozenset(roots)


def mint_root_id(
    prefix: str,
    minted: Collection[str],
    *,
    rng: random.Random | None = None,
    target: float = MAX_COLLISION_PROBABILITY,
) -> str:
    """Mint a fresh top-level record id, ``<prefix>-<root>``.

    Args:
        prefix: The ledger's prefix, ``[a-z][a-z0-9]*``.
        minted: **Every** id ever minted under this ledger, tombstones included
            (:func:`minted_ever`). A candidate matching one of these is discarded, so
            an id is never reused.
        rng: Source of randomness; defaults to :class:`random.SystemRandom`. A seeded
            :class:`random.Random` makes a mint reproducible in a test.
        target: The collision budget the root length is sized against.

    Raises:
        IdError: *prefix* cannot appear in an id.
        IdSpaceExhaustedError: no free candidate up to :data:`MAX_ROOT_LENGTH`.
    """
    validate_prefix(prefix)
    draw = rng if rng is not None else _SYSTEM_RANDOM
    taken = frozenset(minted)
    length = root_length_for(len(root_ids(taken, prefix)) + 1, target=target)
    while length <= MAX_ROOT_LENGTH:
        for _ in range(MINT_ATTEMPTS):
            root = "".join(draw.choice(ALPHABET) for _ in range(length))
            candidate = f"{prefix}{PREFIX_SEP}{root}"
            if candidate not in taken:
                return candidate
        # Every draw at this length was already taken. Growing beats retrying: the
        # population has outrun the length the budget sized, and a longer root is the
        # remedy the budget itself prescribes.
        length += 1
    raise IdSpaceExhaustedError(
        f"no free root of up to {MAX_ROOT_LENGTH} characters under prefix {prefix!r} "
        f"after {MINT_ATTEMPTS} draws per length"
    )


def next_child_id(parent_id: str, minted: Collection[str]) -> str:
    """The next child id under *parent_id*, ``<parent>.<n>``.

    *n* is one past the highest index ever used, taken over *minted* rather than over
    the live children, so a deleted child's index is not handed out again. Nesting is
    free: any record id, child or root, is a valid parent.

    Raises:
        IdError: *parent_id* is not a record id.
    """
    validate_record_id(parent_id)
    head = f"{parent_id}{CHILD_SEP}"
    highest = 0
    for value in minted:
        if not value.startswith(head):
            continue
        index = value[len(head) :].split(CHILD_SEP, 1)[0]
        if _INDEX_PATTERN.match(index):
            highest = max(highest, int(index))
    return f"{head}{highest + 1}"


def evidence_id(
    record_id: str,
    kind: str = "",
    content: str | None = "",
    *,
    family: str = "",
    generation: int = 1,
) -> str:
    """The content-derived id of one immutable fact recorded on *record_id*.

    Recording the same fact twice yields the same id, which is what makes the write
    idempotent instead of duplicated. This reproduces all three evidence-id shapes the
    engine already ships, bit for bit — ``tests/test_kit_tracker_ids.py`` asserts the
    equality rather than describing it:

    - ``decisions.decision_id_for(i, kind, question, gen)`` is
      ``evidence_id(i, kind, question, generation=gen)``
    - ``run_record.marker_id(i, sha, phase, attempt)`` is
      ``evidence_id(i, phase, sha, family="run", generation=attempt)``
    - ``run_record.cost_marker_id(i)`` is ``evidence_id(i, family="cost", content=None)``

    Args:
        record_id: The record the fact is about.
        kind: The digest's namespace — what *sort* of fact this is. Hashed, never
            embedded, so it may be free text.
        content: The fact itself, hashed. ``None`` names a **singleton**: one such fact
            per record, with nothing to key on, so *family* alone is the id.
        family: Optional visible label, ``[a-z][a-z0-9]*``, distinguishing families of
            evidence at a glance. Required when *content* is ``None``.
        generation: ``>1`` names a genuine re-recording of an identical fact — a
            re-opened decision, a re-run dispatch — which needs its own id rather than
            collapsing into the first.

    Raises:
        IdError: *record_id*, *family* or *generation* cannot appear in an id, or there
            is no fact to key on at all.
    """
    validate_record_id(record_id)
    if family and not FAMILY_PATTERN.match(family):
        raise IdError(f"evidence family {family!r} must match {FAMILY_PATTERN.pattern}")
    if generation < 1:
        raise IdError(f"generation must be at least 1, got {generation}")
    if content is None:
        if not family:
            raise IdError("a singleton evidence id needs a family: it has no content to key on")
        return f"{record_id}{EVIDENCE_SEP}{family}"
    if not kind and not content:
        # Refused rather than digesting ``":"``: every record would otherwise share one
        # such id, which reads as evidence and carries none. A singleton is the supported
        # way to say "one fact per record", and it returned above.
        raise IdError("an evidence id needs a kind or content to derive from")
    digest = hashlib.sha256(f"{kind}:{content}".encode()).hexdigest()[:DIGEST_CHARS]
    suffix = digest if generation == 1 else f"{digest}-{generation}"
    stem = f"{family}-{suffix}" if family else suffix
    return f"{record_id}{EVIDENCE_SEP}{stem}"


def record_id_of(evidence: str) -> str:
    """The record an evidence id belongs to.

    Raises:
        IdError: *evidence* is not an evidence id.
    """
    record_id, sep, _ = evidence.partition(EVIDENCE_SEP)
    if not sep or not is_evidence_id(evidence):
        raise IdError(f"{evidence!r} is not an evidence id: expected {EVIDENCE_ID_PATTERN.pattern}")
    return record_id
