from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

TRIGGER_HEADING = "## Trigger"
ACCEPTANCE_HEADING = "## Acceptance Criteria"
REQUIREMENTS_HEADING = "## Requirements"

ACCEPTANCE_FIELD = "acceptance_criteria"
REQUIREMENTS_FIELD = "requirements"
DESCRIPTION_FIELD = "description"

SHAPED_UNDER_FIELD = "shaped_under"
SHAPING_RULE = "dor.v2"

JOB_STORY_EXAMPLE = "When <situation>, I want to <motivation>, so I can <outcome>."
USER_STORY_EXAMPLE = "As a <persona>, I want <goal>, so that <benefit>."

_SPAN = 400
_JOB_STORY = re.compile(
    rf"\bwhen\b.{{0,{_SPAN}}}?\bi want\b.{{0,{_SPAN}}}?\bso (?:i|we) can\b",
    re.IGNORECASE | re.DOTALL,
)
_USER_STORY = re.compile(
    rf"\bas an?\b.{{0,200}}?\bi want\b.{{0,{_SPAN}}}?\bso that\b",
    re.IGNORECASE | re.DOTALL,
)

_PLACEHOLDER = re.compile(r"<[^>]+>|\bTODO\b")
_BULLET = re.compile(r"^- (.+)$")

JOB_VOICE = "job"
USER_VOICE = "user"


def trigger_voice(description):

    for voice, pattern in ((JOB_VOICE, _JOB_STORY), (USER_VOICE, _USER_STORY)):
        for match in pattern.finditer(description):
            if not _PLACEHOLDER.search(match.group(0)):
                return voice
    return None


def section_entries(description: str, heading: str):

    entries = []
    inside = False
    for line in description.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            inside = stripped == heading
            continue
        if inside:
            match = _BULLET.match(stripped)
            if match:
                entries.append(match.group(1).strip())
    return tuple(entries)


def states_something(text) -> bool:
    return bool(isinstance(text, str) and text.strip()) and not _PLACEHOLDER.search(text)


def _held(record: Mapping[str, object], field: str, heading: str, closed: bool) -> bool:

    value = record.get(field)
    if isinstance(value, str) and states_something(value):
        return True
    if isinstance(value, (list, tuple)) and any(states_something(one) for one in value):
        return True
    if not closed:
        return False
    described = record.get(DESCRIPTION_FIELD)
    body = described if isinstance(described, str) else ""
    return any(states_something(entry) for entry in section_entries(body, heading))


SECTIONS = (
    (ACCEPTANCE_HEADING, ACCEPTANCE_FIELD),
    (REQUIREMENTS_HEADING, REQUIREMENTS_FIELD),
)

CONDITIONS = (TRIGGER_HEADING, *(heading for heading, _field in SECTIONS))


def owed(record: Mapping[str, object], *, closed: bool = False) -> tuple:

    described = record.get(DESCRIPTION_FIELD)
    body = described if isinstance(described, str) else ""
    missing = [] if trigger_voice(body) is not None else [TRIGGER_HEADING]
    missing += [heading for heading, field in SECTIONS if not _held(record, field, heading, closed)]
    return tuple(missing)


def minted_under_the_rule(record: Mapping[str, object]) -> bool:

    return bool(record.get(SHAPED_UNDER_FIELD))


def refused(record: Mapping[str, object], *, closed: bool = False) -> tuple:

    missing = owed(record, closed=closed)
    if minted_under_the_rule(record):
        return missing
    return tuple(one for one in missing if one != REQUIREMENTS_HEADING)


def shaped(record: Mapping[str, object], *, closed: bool = False) -> bool:
    return not refused(record, closed=closed)


def remedy(missing: Sequence[str]) -> str:

    parts = []
    for name in missing:
        if name == TRIGGER_HEADING:
            parts.append(
                f"state the trigger in either voice - a situation, {JOB_STORY_EXAMPLE!r}, "
                f"or a persona, {USER_STORY_EXAMPLE!r}. A persona is never required: where "
                f"a situation triggers the work and no person wants it, inventing a persona "
                f"is the defect"
            )
        elif name == ACCEPTANCE_HEADING:
            parts.append(
                f"state the acceptance criteria as `--acceptance` or a `{ACCEPTANCE_HEADING}` "
                f"section of `- ` bullets; they are what a check is derived from, so a "
                f"placeholder counts as absent"
            )
        else:
            parts.append(
                f"state the requirements as `--requirements` or a `{REQUIREMENTS_HEADING}` "
                f"section of `- ` bullets; they are the standard validation judges the "
                f"built thing against"
            )
    return "; ".join(parts)
