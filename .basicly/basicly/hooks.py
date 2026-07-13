"""Project catalog git-hook scripts and their manager wiring into a consumer repo.

The catalog describes hooks tool-agnostically in ``hooks.yaml``; this module
renders that into a hook manager's native config. Only pre-commit is supported
today (``.pre-commit-config.yaml``), and the managed hooks are confined to a
single ``repo: local`` block so foreign repos/hooks the consumer already has are
never clobbered. See docs/architecture.md §4.2, §11.6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .catalog import bundled_catalog_root

HOOKS_MANIFEST = "hooks.yaml"
PRECOMMIT_CONFIG = ".pre-commit-config.yaml"


@dataclass(frozen=True)
class HookSpec:
    """A single catalog hook, described independently of any hook manager."""

    id: str
    script: str
    stage: str
    pass_filenames: bool = False
    always_run: bool = False


@dataclass
class HookSyncResult:
    """Files written vs. left unchanged by a hooks-build run."""

    written: list[Path] = field(default_factory=list)
    unchanged: list[Path] = field(default_factory=list)


def _catalog_hooks_dir() -> Path:
    return bundled_catalog_root() / "hooks"


def load_hook_specs(hooks_dir: Path | None = None) -> list[HookSpec]:
    """Load hook specs from ``hooks.yaml`` in the given (or bundled) hooks dir."""
    hooks_dir = hooks_dir or _catalog_hooks_dir()
    manifest = hooks_dir / HOOKS_MANIFEST
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    entries = data.get("hooks")
    if not isinstance(entries, list):
        raise ValueError(f"{manifest}: 'hooks' must be a list")

    specs: list[HookSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{manifest}: each hook must be a mapping")
        specs.append(
            HookSpec(
                id=str(entry["id"]),
                script=str(entry["script"]),
                stage=str(entry["stage"]),
                pass_filenames=bool(entry.get("pass_filenames", False)),
                always_run=bool(entry.get("always_run", False)),
            )
        )
    return specs


def _hook_entry(spec: HookSpec, hooks_relpath: str) -> dict:
    entry: dict = {
        "id": spec.id,
        "name": spec.id,
        "entry": f"uv run python {hooks_relpath}/{spec.script}",
        "language": "system",
        "stages": [spec.stage],
        "pass_filenames": spec.pass_filenames,
    }
    if spec.always_run:
        entry["always_run"] = True
    return entry


def merge_precommit_config(
    existing: dict | None,
    specs: list[HookSpec],
    hooks_relpath: str,
) -> dict:
    """Return a pre-commit config with basicly's managed hooks merged in.

    Managed hooks (matched by id) are stripped from every ``local`` repo and a
    single fresh managed block is appended, so re-running is idempotent and
    foreign repos/hooks are preserved untouched.
    """
    config = dict(existing) if isinstance(existing, dict) else {}
    managed_ids = {spec.id for spec in specs}

    kept: list = []
    for repo in config.get("repos") or []:
        if isinstance(repo, dict) and repo.get("repo") == "local":
            hooks = [
                hook
                for hook in (repo.get("hooks") or [])
                if not (isinstance(hook, dict) and hook.get("id") in managed_ids)
            ]
            if hooks:
                kept.append({**repo, "hooks": hooks})
            # A local repo left empty was fully basicly-managed; drop it.
        else:
            kept.append(repo)

    kept.append({"repo": "local", "hooks": [_hook_entry(spec, hooks_relpath) for spec in specs]})
    config["repos"] = kept
    return config


def render_precommit_config(
    existing_text: str | None,
    specs: list[HookSpec],
    hooks_relpath: str,
) -> str:
    """Render the merged pre-commit config to deterministic YAML text."""
    existing = yaml.safe_load(existing_text) if existing_text else None
    base = existing if isinstance(existing, dict) else None
    merged = merge_precommit_config(base, specs, hooks_relpath)
    return yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)


def _write_if_changed(path: Path, content: bytes, result: HookSyncResult) -> None:
    if path.exists() and path.read_bytes() == content:
        result.unchanged.append(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    result.written.append(path)


def _iter_catalog_files(src: Path):
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        yield path


def sync_hooks(repo_root: Path, core_hooks_dir: Path) -> HookSyncResult:
    """Materialize hook scripts and merge the pre-commit wiring.

    ``core_hooks_dir`` is the on-disk destination (e.g. ``.basicly/core/hooks``).
    Scripts are copied from the bundled catalog (write-if-changed); when the
    catalog is its own source (dogfood repo) the copy is skipped.
    """
    result = HookSyncResult()
    src = _catalog_hooks_dir()
    dst = repo_root / core_hooks_dir

    if src.resolve() != dst.resolve():
        for path in _iter_catalog_files(src):
            _write_if_changed(dst / path.relative_to(src), path.read_bytes(), result)

    specs = load_hook_specs(src)
    hooks_relpath = core_hooks_dir.as_posix()
    config_path = repo_root / PRECOMMIT_CONFIG
    existing_text = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    rendered = render_precommit_config(existing_text, specs, hooks_relpath)
    _write_if_changed(config_path, rendered.encode("utf-8"), result)

    return result


def check_hooks(repo_root: Path, core_hooks_dir: Path) -> list[tuple[Path, str]]:
    """Return (path, reason) for any hook script or wiring that is out of sync."""
    mismatches: list[tuple[Path, str]] = []
    src = _catalog_hooks_dir()
    dst = repo_root / core_hooks_dir

    if src.resolve() != dst.resolve():
        for path in _iter_catalog_files(src):
            target = dst / path.relative_to(src)
            if not target.exists():
                mismatches.append((target, "missing"))
            elif target.read_bytes() != path.read_bytes():
                mismatches.append((target, "differs from catalog"))

    specs = load_hook_specs(src)
    config_path = repo_root / PRECOMMIT_CONFIG
    existing_text = config_path.read_text(encoding="utf-8") if config_path.exists() else None
    expected = render_precommit_config(existing_text, specs, core_hooks_dir.as_posix())
    if existing_text is None:
        mismatches.append((config_path, "missing"))
    elif existing_text != expected:
        mismatches.append((config_path, "managed hooks out of sync"))

    return mismatches
