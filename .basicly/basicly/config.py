"""Project path configuration for basicly."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_FILE = "basicly.toml"

# Scaffolded into a consumer repo by `basicly init`. Kept next to the defaults
# below; test_config asserts parsing this yields exactly the built-in defaults,
# so the two can never drift apart.
DEFAULT_CONFIG_TOML = """\
# basicly path wiring. Managed core catalog is materialized by `basicly init`
# and refreshed by `basicly update`; the overlay is always yours to edit.
[paths]
core_fragments = ".basicly/core/fragments"
overlay_fragments = [".basicly-local/fragments"]
targets = ".basicly/core/targets"
templates = ".basicly/core/templates"
manifest = ".basicly/generated-manifest.json"
"""


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved paths used by the projector CLI."""

    core_fragments_dir: Path
    overlay_fragments_dirs: tuple[Path, ...]
    targets_dir: Path
    templates_dir: Path
    manifest_path: Path
    legacy_fragments_dir: Path

    @property
    def core_root(self) -> Path:
        """Root of the managed core catalog, derived from the fragments dir.

        Every command that touches the core tree (init materialization, hooks
        projection) must use this single notion so a custom `core_fragments`
        in basicly.toml relocates the whole catalog consistently.
        """
        return self.core_fragments_dir.parent


def load_project_paths(repo_root: Path) -> ProjectPaths:
    """Load path settings from basicly.toml, falling back to defaults."""
    defaults = ProjectPaths(
        core_fragments_dir=Path(".basicly/core/fragments"),
        overlay_fragments_dirs=(Path(".basicly-local/fragments"),),
        targets_dir=Path(".basicly/core/targets"),
        templates_dir=Path(".basicly/core/templates"),
        manifest_path=Path(".basicly/generated-manifest.json"),
        legacy_fragments_dir=Path(".basicly/fragments"),
    )

    config_path = repo_root / CONFIG_FILE
    if not config_path.exists():
        return defaults

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    if not isinstance(paths, dict):
        return defaults

    core_fragments_dir = _parse_path_value(paths, "core_fragments", defaults.core_fragments_dir)
    targets_dir = _parse_path_value(paths, "targets", defaults.targets_dir)
    templates_dir = _parse_path_value(paths, "templates", defaults.templates_dir)
    manifest_path = _parse_path_value(paths, "manifest", defaults.manifest_path)

    overlay_fragments = _parse_overlay_paths(paths)
    if overlay_fragments is None:
        overlay_fragments_dirs = defaults.overlay_fragments_dirs
    else:
        overlay_fragments_dirs = tuple(overlay_fragments)

    return ProjectPaths(
        core_fragments_dir=core_fragments_dir,
        overlay_fragments_dirs=overlay_fragments_dirs,
        targets_dir=targets_dir,
        templates_dir=templates_dir,
        manifest_path=manifest_path,
        legacy_fragments_dir=defaults.legacy_fragments_dir,
    )


def _parse_path_value(paths: dict, key: str, default: Path) -> Path:
    value = paths.get(key)
    if isinstance(value, str) and value.strip():
        return Path(value)
    return default


def _parse_overlay_paths(paths: dict) -> list[Path] | None:
    value = paths.get("overlay_fragments")
    if value is None:
        return None

    if isinstance(value, str) and value.strip():
        return [Path(value)]

    if isinstance(value, list):
        parsed = [Path(item) for item in value if isinstance(item, str) and item.strip()]
        return parsed if parsed else None

    return None
