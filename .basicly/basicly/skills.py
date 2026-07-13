"""Skill collection discovery and projection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from .loader import FRONT_MATTER_RE
from .schema import ValidationError

SKILLS_SOURCE_DIR = Path(".basicly/core/skills")
SKILL_FILE_NAME = "SKILL.md"
DEFAULT_SKILL_ROOTS = (
    Path(".claude/skills"),
    Path(".github/skills"),
    Path(".agents/skills"),
)


@dataclass(frozen=True)
class SkillDefinition:
    """A source skill loaded from .basicly/core/skills."""

    slug: str
    name: str
    description: str
    source_path: Path


@dataclass(frozen=True)
class SkillSyncResult:
    """A summary of what changed while syncing skills."""

    written: list[Path]
    unchanged: list[Path]


def discover_skills(
    repo_root: Path,
    source_dir: Path = SKILLS_SOURCE_DIR,
) -> list[SkillDefinition]:
    """Load and validate all skills from the source collection directory."""
    base_dir = repo_root / source_dir
    if not base_dir.exists():
        return []

    skills: list[SkillDefinition] = []
    seen_slugs: set[str] = set()

    for path in sorted(base_dir.glob(f"*/{SKILL_FILE_NAME}")):
        slug = path.parent.name
        if slug in seen_slugs:
            raise ValidationError(f"duplicate skill slug '{slug}'", path)
        seen_slugs.add(slug)

        text = path.read_text(encoding="utf-8")
        match = FRONT_MATTER_RE.match(text)
        if not match:
            raise ValidationError("missing or invalid YAML front matter", path)

        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            raise ValidationError(f"invalid YAML front matter: {exc}", path) from exc

        if not isinstance(frontmatter, dict):
            raise ValidationError("front matter must be a YAML mapping", path)

        name = frontmatter.get("name")
        description = frontmatter.get("description")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("missing required frontmatter field 'name'", path)
        if not isinstance(description, str) or not description.strip():
            raise ValidationError("missing required frontmatter field 'description'", path)

        skills.append(
            SkillDefinition(
                slug=slug,
                name=name.strip(),
                description=description.strip(),
                source_path=path,
            )
        )

    return skills


def resolve_skill_roots(
    repo_root: Path,
    roots: list[str] | None,
    use_default_roots: bool,
) -> list[Path]:
    """Resolve output roots for projected skills."""
    if roots:
        candidates = [Path(item) for item in roots]
    elif use_default_roots:
        candidates = list(DEFAULT_SKILL_ROOTS)
    else:
        # Keep default behavior minimal for this repo, but allow expansion with --all-default-roots.
        candidates = [DEFAULT_SKILL_ROOTS[0]]

    resolved: list[Path] = []
    seen: set[str] = set()

    for root in candidates:
        absolute_root = root if root.is_absolute() else repo_root / root
        key = str(absolute_root)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(absolute_root)

    return resolved


def sync_skills(
    repo_root: Path,
    roots: list[Path],
    source_dir: Path = SKILLS_SOURCE_DIR,
) -> SkillSyncResult:
    """Copy source skills into destination roots without deleting extra files."""
    skills = discover_skills(repo_root, source_dir)
    written: list[Path] = []
    unchanged: list[Path] = []

    for skill in skills:
        source_text = skill.source_path.read_text(encoding="utf-8")
        for root in roots:
            target_path = root / skill.slug / SKILL_FILE_NAME
            if target_path == skill.source_path:
                unchanged.append(target_path)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and target_path.read_text(encoding="utf-8") == source_text:
                unchanged.append(target_path)
                continue

            target_path.write_text(source_text, encoding="utf-8")
            written.append(target_path)

    return SkillSyncResult(written=written, unchanged=unchanged)


def check_synced_skills(
    repo_root: Path,
    roots: list[Path],
    source_dir: Path = SKILLS_SOURCE_DIR,
) -> list[tuple[Path, str]]:
    """Return missing or stale skill files for the selected destination roots."""
    skills = discover_skills(repo_root, source_dir)
    mismatches: list[tuple[Path, str]] = []

    for skill in skills:
        source_text = skill.source_path.read_text(encoding="utf-8")
        for root in roots:
            target_path = root / skill.slug / SKILL_FILE_NAME
            if not target_path.exists():
                mismatches.append((target_path, "missing"))
                continue
            if target_path.read_text(encoding="utf-8") != source_text:
                mismatches.append((target_path, "content mismatch"))

    return mismatches
