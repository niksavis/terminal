from __future__ import annotations

import hashlib
import math
import random
import re
from collections.abc import Collection, Iterable

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
RADIX = len(ALPHABET)

PREFIX_SEP = "-"
CHILD_SEP = "."
EVIDENCE_SEP = "#"

MAX_COLLISION_PROBABILITY = 1e-4

MIN_ROOT_LENGTH = 4
MAX_ROOT_LENGTH = 12

MINT_ATTEMPTS = 16

DIGEST_CHARS = 10

_RECORD = r"[a-z][a-z0-9]*-[a-z0-9]+(?:\.[0-9]+)*"
_FAMILY = r"[a-z][a-z0-9]*"
_DIGEST = rf"[0-9a-f]{{{DIGEST_CHARS}}}"

PREFIX_PATTERN = re.compile(rf"^{_FAMILY}$")
FAMILY_PATTERN = re.compile(rf"^{_FAMILY}$")
RECORD_ID_PATTERN = re.compile(rf"^{_RECORD}$")
EVIDENCE_ID_PATTERN = re.compile(
    rf"^{_RECORD}{EVIDENCE_SEP}(?:(?:{_FAMILY}-)?{_DIGEST}(?:-[0-9]+)?|{_FAMILY})$"
)

_INDEX_PATTERN = re.compile(r"^[0-9]+$")

_SYSTEM_RANDOM = random.SystemRandom()


class IdError(ValueError):
    pass


class IdSpaceExhaustedError(IdError):
    pass


def collision_probability(population: int, length: int) -> float:

    if population < 2:
        return 0.0
    n = float(population)
    return -math.expm1(-(n * n) / (2.0 * float(RADIX**length)))


def max_population(length: int, *, target: float = MAX_COLLISION_PROBABILITY) -> int:

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

    if PREFIX_SEP in prefix:
        raise IdError(
            f"prefix {prefix!r} contains {PREFIX_SEP!r}: the commit-message gate reads "
            f"the first hyphen as the prefix boundary, so the id would be refused"
        )
    if not PREFIX_PATTERN.match(prefix):
        raise IdError(f"prefix {prefix!r} must match {PREFIX_PATTERN.pattern}")
    return prefix


def validate_record_id(record_id: str) -> str:
    if not RECORD_ID_PATTERN.match(record_id):
        raise IdError(f"{record_id!r} is not a record id: expected {RECORD_ID_PATTERN.pattern}")
    return record_id


def is_record_id(value: str) -> bool:
    return bool(RECORD_ID_PATTERN.match(value))


def is_evidence_id(value: str) -> bool:
    return bool(EVIDENCE_ID_PATTERN.match(value))


def minted_ever(live: Iterable[str], tombstoned: Iterable[str] = ()) -> frozenset[str]:

    return frozenset(live) | frozenset(tombstoned)


def root_ids(minted: Iterable[str], prefix: str) -> frozenset[str]:

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
        length += 1
    raise IdSpaceExhaustedError(
        f"no free root of up to {MAX_ROOT_LENGTH} characters under prefix {prefix!r} "
        f"after {MINT_ATTEMPTS} draws per length"
    )


def next_child_id(parent_id: str, minted: Collection[str]) -> str:

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
        raise IdError("an evidence id needs a kind or content to derive from")
    digest = hashlib.sha256(f"{kind}:{content}".encode()).hexdigest()[:DIGEST_CHARS]
    suffix = digest if generation == 1 else f"{digest}-{generation}"
    stem = f"{family}-{suffix}" if family else suffix
    return f"{record_id}{EVIDENCE_SEP}{stem}"


def record_id_of(evidence: str) -> str:

    record_id, sep, _ = evidence.partition(EVIDENCE_SEP)
    if not sep or not is_evidence_id(evidence):
        raise IdError(f"{evidence!r} is not an evidence id: expected {EVIDENCE_ID_PATTERN.pattern}")
    return record_id
