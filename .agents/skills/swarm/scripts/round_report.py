from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

USAGE_LIMIT = 1024 * 1024
DISPATCH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"usage manifest repeats field {key!r}")
        result[key] = value
    return result


def _metric_value(value: Any, name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"usage {name} must be a nonnegative number or null")
    if name == "tokens" and not isinstance(value, int):
        raise ValueError("usage tokens must be an integer or null")
    try:
        finite = math.isfinite(value)
    except OverflowError as error:
        raise ValueError(f"usage {name} exceeds the numeric range") from error
    if not finite:
        raise ValueError(f"usage {name} must be finite")
    return value


def _agent_record(agent: Any, lenses: list[str], previous_ids: set[str]) -> dict[str, Any]:
    fields = {"id", "lens", "role", "source", "cost_kind", "tokens", "cost_usd", "duration_s"}
    if not isinstance(agent, dict) or set(agent) - fields:
        raise ValueError("usage agents require id, lens, role, source, cost_kind and metric fields")
    identifier = agent.get("id")
    if not isinstance(identifier, str) or not DISPATCH_ID.fullmatch(identifier):
        raise ValueError("usage dispatch id must be a nonempty host identifier")
    if identifier in previous_ids:
        raise ValueError("usage dispatch id was already recorded")
    role = agent.get("role")
    if not isinstance(role, str) or role not in {"reviewer", "verifier"}:
        raise ValueError("usage role must be reviewer or verifier")
    lens = agent.get("lens")
    if lens not in lenses and not (lens is None and role == "verifier"):
        raise ValueError("usage lens must name a requested lens")
    metrics = {
        name: _metric_value(agent.get(name), name) for name in ("tokens", "cost_usd", "duration_s")
    }
    source = agent.get("source")
    if source is not None and (
        not isinstance(source, str)
        or not source.strip()
        or len(source) > 1024
        or any(ord(char) < 32 for char in source)
    ):
        raise ValueError("usage source must be a nonempty single-line reference")
    if any(value is not None for value in metrics.values()) and source is None:
        raise ValueError("usage metrics require their host source reference")
    kind = agent.get("cost_kind")
    if (
        kind is not None and (not isinstance(kind, str) or kind not in {"reported", "cli-estimate"})
    ) or (metrics["cost_usd"] is not None and kind is None):
        raise ValueError("usage cost_kind must label a known cost as reported or cli-estimate")
    previous_ids.add(identifier)
    return {
        "id": identifier,
        "role": role,
        "lens": lens,
        "source": source,
        "cost_kind": kind,
        **metrics,
    }


def _usage_records(
    path: Path | None, hashes: dict[str, str], previous_ids: set[str]
) -> tuple[list[dict[str, Any]], str | None]:
    if path is None:
        return [], None
    if any(part.casefold().startswith(".env") for part in (*path.parts, *path.resolve().parts)):
        raise ValueError("usage requires a JSON manifest, not an environment file")
    if path.is_symlink():
        raise ValueError("usage manifest must not be a symlink")
    with path.open("rb") as stream:
        raw = stream.read(USAGE_LIMIT + 1)
    if len(raw) > USAGE_LIMIT:
        raise ValueError("usage manifest exceeds the read limit")
    data = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != {"reports_sha256", "agents"}:
        raise ValueError("usage manifest requires reports_sha256 and agents")
    if data["reports_sha256"] != hashes:
        raise ValueError("usage manifest does not match this round's replies")
    if not isinstance(data["agents"], list):
        raise ValueError("usage agents must be a list")
    records = [_agent_record(agent, list(hashes), previous_ids) for agent in data["agents"]]
    return records, hashlib.sha256(raw).hexdigest()


def _usage_summary(records: list[dict[str, Any]], lenses: list[str]) -> dict[str, Any]:
    covered = {agent["lens"] for agent in records if agent["role"] == "reviewer"}
    missing = sorted(set(lenses) - covered)
    summary: dict[str, Any] = {
        "scope": "reported agents only",
        "agents": records,
        "missing_reviewers": missing,
        "cost_kinds": sorted({
            agent["cost_kind"] for agent in records if agent["cost_usd"] is not None
        }),
    }
    for field, label in [
        ("tokens", "tokens"),
        ("cost_usd", "cost_usd"),
        ("duration_s", "agent_seconds"),
    ]:
        values = [agent[field] for agent in records if agent[field] is not None]
        try:
            known = (sum(values) if field == "tokens" else math.fsum(values)) if values else None
        except OverflowError as error:
            raise ValueError("usage aggregate exceeds the numeric range") from error
        summary[f"known_{label}"] = known
        summary[label] = known if not missing and len(values) == len(records) else None
    return summary


def round_metrics(
    directory: Path,
    lenses: list[str],
    previous: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    usage_path: Path | None,
) -> dict[str, Any]:
    hashes = {
        lens: hashlib.sha256((directory / f"{lens}.md").read_bytes()).hexdigest() for lens in lenses
    }
    previous_ids = {
        agent["id"]
        for row in previous
        for agent in row.get("metrics", {}).get("usage", {}).get("agents", [])
    }
    earlier = {
        identifier
        for row in previous
        for identifier in row.get("metrics", {}).get("findings", {}).get("cited_important_ids", [])
    }
    important = [finding for finding in findings if finding["severity"] == "important"]
    identities = {
        hashlib.sha256(
            json.dumps(
                [" ".join(str(finding.get(key, "")).split()) for key in ("claim", "evidence")],
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        for finding in important
        if finding["cited"]
    }
    records, usage_hash = _usage_records(usage_path, hashes, previous_ids)
    return {
        "reports_sha256": hashes,
        "usage_sha256": usage_hash,
        "findings": {
            "reported_important": len(important),
            "uncited_important": sum(not finding["cited"] for finding in important),
            "distinct_cited_important": len(identities),
            "repeated_cited_important": len(identities & earlier),
            "cited_important_ids": sorted(identities),
        },
        "usage": _usage_summary(records, lenses),
    }


def print_rounds(state: dict[str, Any]) -> None:
    print("Grades come from reviewer reports. Usage covers reported agents only.")
    print("| round | property | grade |\n|---|---|---|")
    for number, row in enumerate(state["rounds"], 1):
        for prop in state["properties"]:
            grade = f"{row['scores'][prop]:g}"
            if row["highs"][prop] != row["scores"][prop]:
                grade += f"-{row['highs'][prop]:g}"
            print(f"| {number} | {prop} | {grade} |")
    print("\n| round | finding metric | count |\n|---|---|---|")
    for number, row in enumerate(state["rounds"], 1):
        findings = row.get("metrics", {}).get("findings", {})
        print(f"| {number} | remaining important reports | {row['important']} |")
        for key in ("distinct_cited_important", "repeated_cited_important", "uncited_important"):
            print(f"| {number} | {key} | {findings.get(key, 'unknown')} |")
    print("\n| round | reported metric | value |\n|---|---|---|")
    for number, row in enumerate(state["rounds"], 1):
        usage = row.get("metrics", {}).get("usage", {})
        for key in (
            "tokens",
            "cost_usd",
            "agent_seconds",
            "known_tokens",
            "known_cost_usd",
            "known_agent_seconds",
        ):
            value = usage.get(key)
            print(f"| {number} | {key} | {value if value is not None else 'unknown'} |")
        kinds = usage.get("cost_kinds", [])
        if kinds:
            print(f"Reported cost kinds for round {number}: {', '.join(kinds)}")
