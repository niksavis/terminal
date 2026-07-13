from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_sync_module():
    """Load the sync-basicly script as a module from its script path."""
    script_path = Path(__file__).resolve().parents[1] / ".scripts" / "sync-basicly.py"
    spec = importlib.util.spec_from_file_location("sync_basicly", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_copy_tree_filtered_skips_bytecode(tmp_path: Path) -> None:
    """Copying must exclude __pycache__ directories and .pyc files."""
    module = _load_sync_module()
    src = tmp_path / "src"
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (src / "pkg" / "__pycache__" / "mod.cpython-314.pyc").write_bytes(b"\x00")
    (src / "stale.pyc").write_bytes(b"\x00")

    dst = tmp_path / "dst"
    copied = module.copy_tree_filtered(src, dst)

    assert copied == 1
    assert (dst / "pkg" / "mod.py").exists()
    assert not (dst / "pkg" / "__pycache__").exists()
    assert not (dst / "stale.pyc").exists()


def test_copy_tree_filtered_replaces_existing_destination(tmp_path: Path) -> None:
    """A pre-existing destination tree must be fully replaced, not merged."""
    module = _load_sync_module()
    src = tmp_path / "src"
    src.mkdir()
    (src / "keep.py").write_text("keep\n", encoding="utf-8")
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "leftover.py").write_text("stale\n", encoding="utf-8")

    module.copy_tree_filtered(src, dst)

    assert (dst / "keep.py").exists()
    assert not (dst / "leftover.py").exists()


def test_remove_excluded_skills_from_catalog_and_projections(tmp_path: Path) -> None:
    """Excluded skills must be removed from the catalog and projected roots."""
    module = _load_sync_module()
    catalog = tmp_path / "core"
    projected = tmp_path / "claude-skills"
    for slug in (*module.EXCLUDED_SKILLS, "tool-git"):
        (catalog / "skills" / slug).mkdir(parents=True)
        (projected / slug).mkdir(parents=True)

    removed = module.remove_excluded_skills(catalog, (projected,))

    assert len(removed) == 2 * len(module.EXCLUDED_SKILLS)
    for slug in module.EXCLUDED_SKILLS:
        assert not (catalog / "skills" / slug).exists()
        assert not (projected / slug).exists()
    assert (catalog / "skills" / "tool-git").exists()
    assert (projected / "tool-git").exists()


def test_update_provenance_text_replaces_first_hash_only() -> None:
    """Only the recorded provenance hash is rewritten; other hashes stay."""
    module = _load_sync_module()
    old = "a" * 40
    other = "b" * 40
    text = f"- Source: commit `{old}`.\n- Unrelated: `{other}`.\n"
    new = "c" * 40

    updated = module.update_provenance_text(text, new)

    assert f"`{new}`" in updated
    assert f"`{old}`" not in updated
    assert f"`{other}`" in updated
