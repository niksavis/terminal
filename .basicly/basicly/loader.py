"""Load and validate fragments and target registries."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .schema import (
    CATEGORIES,
    DEFAULT_SCOPE,
    PRIORITY_MAP,
    STATUSES,
    Fragment,
    OutputDef,
    Target,
    ValidationError,
)

FRONT_MATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n(.*)$",
    re.DOTALL,
)

REQUIRED_FRAGMENT_FIELDS = {"id", "description", "category", "applies_to"}


def load_fragments(fragments_dir: Path, target_names: set[str]) -> list[Fragment]:
    """Load all fragment files from the fragments directory."""
    return load_fragments_from_roots([(fragments_dir, None)], target_names)


def load_fragments_from_roots(
    fragment_roots: list[tuple[Path, str | None]],
    target_names: set[str],
) -> list[Fragment]:
    """Load all fragment files from one or more fragment roots."""
    fragments: list[Fragment] = []
    seen_ids: dict[str, Path] = {}

    for root, source_hint in fragment_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.fragment.md")):
            fragment = _load_fragment(path, source_hint)
            _validate_fragment(fragment, path, target_names)
            if fragment.id in seen_ids:
                first_path = seen_ids[fragment.id]
                raise ValidationError(
                    f"duplicate fragment id '{fragment.id}' (first defined in {first_path})",
                    path,
                )
            seen_ids[fragment.id] = path
            fragments.append(fragment)

    return fragments


def _load_fragment(path: Path, source_hint: str | None = None) -> Fragment:
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValidationError("missing or invalid YAML front matter", path)

    try:
        front = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML front matter: {exc}", path) from exc

    if not isinstance(front, dict):
        raise ValidationError("front matter must be a YAML mapping", path)

    body = match.group(2).strip("\n")
    scope = front.get("scope", {})
    scope_paths = scope.get("paths", list(DEFAULT_SCOPE)) if scope else list(DEFAULT_SCOPE)
    inferred_source = source_hint or _infer_source_from_path(path)
    source = front.get("source", inferred_source)

    return Fragment(
        id=front.get("id", ""),
        description=front.get("description", ""),
        category=front.get("category", ""),
        applies_to=front.get("applies_to", []),
        priority=front.get("priority", "medium"),
        scope_paths=scope_paths,
        tags=front.get("tags", []),
        status=front.get("status", "active"),
        title=front.get("title"),
        body=body,
        source_path=path,
        source=source,
        override=bool(front.get("override", False)),
        replaces=front.get("replaces", []),
        extends=front.get("extends", []),
    )


def _infer_source_from_path(path: Path) -> str:
    """Infer source based on path conventions when front matter omits source."""
    parts = {part.lower() for part in path.parts}
    if ".basicly-local" in parts or "user" in parts:
        return "user"
    return "core"


def _validate_fragment(
    fragment: Fragment,
    path: Path,
    target_names: set[str],
) -> None:
    missing = REQUIRED_FRAGMENT_FIELDS - {
        k
        for k, v in {
            "id": fragment.id,
            "description": fragment.description,
            "category": fragment.category,
            "applies_to": fragment.applies_to,
        }.items()
        if v
    }
    if missing:
        raise ValidationError(
            f"missing required fields: {', '.join(sorted(missing))}",
            path,
        )

    if fragment.category not in CATEGORIES:
        raise ValidationError(f"unknown category '{fragment.category}'", path)

    if fragment.priority not in PRIORITY_MAP:
        raise ValidationError(f"unknown priority '{fragment.priority}'", path)

    if fragment.status not in STATUSES:
        raise ValidationError(f"unknown status '{fragment.status}'", path)

    for target in fragment.applies_to:
        if target != "all" and target not in target_names:
            raise ValidationError(
                f"applies_to value '{target}' is not a registered target",
                path,
            )

    if fragment.source not in {"core", "user"}:
        raise ValidationError(f"source must be 'core' or 'user', got '{fragment.source}'", path)

    if not isinstance(fragment.override, bool):
        raise ValidationError("override must be a boolean", path)

    if not isinstance(fragment.replaces, list) or not all(
        isinstance(x, str) for x in fragment.replaces
    ):
        raise ValidationError("replaces must be a list of strings", path)

    if not isinstance(fragment.extends, list) or not all(
        isinstance(x, str) for x in fragment.extends
    ):
        raise ValidationError("extends must be a list of strings", path)


def load_targets(targets_dir: Path) -> list[Target]:
    """Load all target registry YAML files."""
    targets: list[Target] = []

    for path in sorted(targets_dir.glob("*.yaml")):
        target = _load_target(path)
        targets.append(target)

    return targets


def _load_target(path: Path) -> Target:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML: {exc}", path) from exc

    outputs: list[OutputDef] = []
    for name, output in (data.get("outputs") or {}).items():
        filter_def = output.get("filter", {})
        outputs.append(
            OutputDef(
                name=name,
                template=output["template"],
                path=output.get("path"),
                path_template=output.get("path_template"),
                applies_to_filter=filter_def.get("applies_to", []),
                has_scope=filter_def.get("has_scope", False),
            )
        )

    return Target(
        name=data["name"],
        enabled=data.get("enabled", True),
        tone=data.get("tone", "directive"),
        max_size_warning=data.get("max_size_warning", 0),
        outputs=outputs,
    )
