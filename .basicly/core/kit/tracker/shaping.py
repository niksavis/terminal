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

REFINE_LABEL = "refine"

JOB_STORY_EXAMPLE = "When <situation>, I want to <motivation>, so I can <outcome>."
USER_STORY_EXAMPLE = "As a <persona>, I want <goal>, so that <benefit>."

_SPAN = 400
_END = rf"(?P<outcome>.{{0,{_SPAN}}}?)(?:[.!?](?=\s|$)|$)"
_JOB_STORY = re.compile(
    rf"\bwhen\b(?P<situation>.{{0,{_SPAN}}}?)\bi want\b"
    rf"(?P<motivation>.{{0,{_SPAN}}}?)\bso (?:i|we) can\b{_END}",
    re.IGNORECASE,
)
_USER_STORY = re.compile(
    rf"\bas an?\b(?P<situation>.{{0,200}}?)\bi want\b"
    rf"(?P<motivation>.{{0,{_SPAN}}}?)\bso that\b{_END}",
    re.IGNORECASE,
)
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n|\n(?=\s*#|\s*[-*] )")

_PLACEHOLDER = re.compile(r"<[^>]+>|\bTODO\b")
_TRIGGER_PLACEHOLDER = re.compile(r"\b(?:todo|tbd|tbc|fixme)\b", re.IGNORECASE)
_CODE_SPAN = re.compile(r"`[^`\n]*`")
_BULLET = re.compile(r"^- (.+)$")

JOB_VOICE = "job"
USER_VOICE = "user"


def _stated_intent(text: str, *, motivation: bool = False) -> bool:
    plain = _CODE_SPAN.sub("", text).strip(" ,.:;!?-_")
    if motivation:
        plain = re.sub(r"^to\b", "", plain, flags=re.IGNORECASE).strip()
    return (
        bool(re.search(r"[^\W_]", plain))
        and not unfilled(text)
        and not _TRIGGER_PLACEHOLDER.fullmatch(plain)
    )


def _trigger(description: str) -> tuple[str, str] | None:
    for paragraph in _PARAGRAPH_BREAK.split(description):
        text = " ".join(paragraph.split())
        for voice, pattern in ((JOB_VOICE, _JOB_STORY), (USER_VOICE, _USER_STORY)):
            for match in pattern.finditer(text):
                if all(
                    _stated_intent(match.group(name), motivation=name == "motivation")
                    for name in ("situation", "motivation", "outcome")
                ):
                    return voice, match.group(0).strip()
    return None


def trigger_voice(description: str) -> str | None:
    found = _trigger(description)
    return found[0] if found else None


def trigger_sentence(description: str) -> str:
    found = _trigger(description)
    return found[1] if found else ""


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


def unfilled(text: str) -> bool:
    return bool(_PLACEHOLDER.search(_CODE_SPAN.sub("", text)))


def states_something(text) -> bool:
    return bool(isinstance(text, str) and text.strip()) and not unfilled(text)


def _held(record: Mapping[str, object], field: str, heading: str, closed: bool) -> bool:

    value = record.get(field)
    if isinstance(value, str) and states_something(value):
        return True
    if isinstance(value, (list, tuple)) and value and all(states_something(one) for one in value):
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


TYPE_FIELD = "issue_type"


def field_of(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", heading.lstrip("#").strip().lower()).strip("_")


def section_text(description: str, heading: str) -> str:

    lines = []
    inside = False
    for line in description.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            inside = stripped == heading
            continue
        if inside and stripped:
            lines.append(stripped)
    return "\n".join(lines)


def required(record: Mapping[str, object], template=None) -> tuple:

    if template is None:
        return CONDITIONS
    kind = record.get(TYPE_FIELD)
    extra = template.for_type(kind if isinstance(kind, str) else "")
    base = CONDITIONS if template.extends else ()
    return tuple(dict.fromkeys((*base, *template.sections, *extra)))


def _meets(record: Mapping[str, object], heading: str, body: str, closed: bool) -> bool:

    if heading == TRIGGER_HEADING:
        return trigger_voice(body) is not None
    known = dict(SECTIONS).get(heading)
    if known is not None:
        return _held(record, known, heading, closed)
    value = record.get(field_of(heading))
    return states_something(value) or states_something(section_text(body, heading))


def meets(record: Mapping[str, object], heading: str, *, closed: bool = False) -> bool:
    described = record.get(DESCRIPTION_FIELD)
    return _meets(record, heading, described if isinstance(described, str) else "", closed)


def owed(record: Mapping[str, object], *, closed: bool = False, template=None, process=()) -> tuple:

    described = record.get(DESCRIPTION_FIELD)
    body = described if isinstance(described, str) else ""
    structural = tuple(
        heading
        for heading in required(record, template)
        if not _meets(record, heading, body, closed)
    )
    return (*structural, *(() if closed else process))


def minted_under_the_rule(record: Mapping[str, object]) -> bool:

    return bool(record.get(SHAPED_UNDER_FIELD))


def refused(
    record: Mapping[str, object], *, closed: bool = False, template=None, process=()
) -> tuple:
    return owed(record, closed=closed, template=template, process=process)


def held_from_ready(
    record: Mapping[str, object], *, labelled: bool, template=None, process=()
) -> bool:
    return labelled or bool(refused(record, template=template, process=process))


def shaped(record: Mapping[str, object], *, closed: bool = False, template=None) -> bool:
    return not refused(record, closed=closed, template=template)


def remedy(missing: Sequence[str]) -> str:

    parts = []
    for name in missing:
        if name == TRIGGER_HEADING:
            parts.append(
                f"state a complete trigger with a situation/persona, motivation/goal and "
                f"outcome/benefit; each part must contain text without placeholders. "
                f"Use either voice - a situation, {JOB_STORY_EXAMPLE!r}, "
                f"or a persona, {USER_STORY_EXAMPLE!r}. A persona is never required: where "
                f"a situation triggers the work and no person wants it, inventing a persona "
                f"is the defect"
            )
        elif name == ACCEPTANCE_HEADING:
            parts.append(
                "state the acceptance criteria as `--acceptance`; they are what a check is "
                "derived from, so a placeholder counts as absent"
            )
        elif name == REQUIREMENTS_HEADING:
            parts.append(
                "state the requirements as `--requirements`; they are the standard "
                "validation judges the built thing against"
            )
        elif name.startswith("## INVEST Review"):
            parts.append(
                f"use review --evidence to record a text rationale for {name.partition(': ')[2]}"
            )
        elif name == "## Conversation":
            parts.append(
                "use review --evidence with actual same-card comment seqs from show comment_log"
            )
        elif name == "## Confirmation Plan":
            parts.append(
                "use review --evidence: checks of criterion, command (an argv list) and expected"
            )
        elif name == "## Completion Confirmation":
            parts.append(
                "use confirm --evidence: checks of criterion, planned command, result, exit_code 0"
            )
        else:
            parts.append(
                f"the template requires `{name}`: add that section to the description, or "
                f"`--field {field_of(name)}=<text>`"
            )
    return "; ".join(parts)


TYPED_HEADINGS = {ACCEPTANCE_HEADING: "--acceptance", REQUIREMENTS_HEADING: "--requirements"}
_FLAGS = TYPED_HEADINGS


def body(kind: str, template=None) -> dict:

    headings = required({TYPE_FIELD: kind}, template)
    flags = {_FLAGS[one]: "- <what is checked>" for one in headings if one in _FLAGS}
    sections = [JOB_STORY_EXAMPLE] if TRIGGER_HEADING in headings else []
    sections += [
        f"{one}\n\n<text>" for one in headings if one != TRIGGER_HEADING and one not in _FLAGS
    ]
    return {"required": list(headings), "description": "\n\n".join(sections), "flags": flags}
