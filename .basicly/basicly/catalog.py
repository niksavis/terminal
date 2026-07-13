"""Locate the managed core catalog shipped with the package.

The catalog (fragments, skills, hooks, targets, templates) is authored at
``.basicly/core/`` and dogfooded there by this repo. The build projects it into
the distribution at ``basicly/catalog/`` (see ``pyproject.toml``
``force-include``), so an installed wheel carries the catalog as package data.

``basicly init``/``update`` copy from :func:`bundled_catalog_root` onto a
consumer repo's disk; the rest of the engine then reads the on-disk copy via
:mod:`basicly.config`.
"""

from __future__ import annotations

from pathlib import Path

CATALOG_DIRNAME = "catalog"


def bundled_catalog_root() -> Path:
    """Return the root of the catalog bundled with this package.

    Prefers the packaged copy at ``basicly/catalog`` (present in an installed
    wheel). Falls back to the authoring source ``.basicly/core`` when running
    from a source checkout or editable install, where the projected copy does
    not exist on disk.
    """
    packaged = Path(__file__).parent / CATALOG_DIRNAME
    if packaged.is_dir():
        return packaged

    # Source checkout / editable dogfood: src/basicly/catalog.py -> repo root.
    source = Path(__file__).resolve().parents[2] / ".basicly" / "core"
    if source.is_dir():
        return source

    raise FileNotFoundError(
        "bundled catalog not found: neither the packaged "
        f"'{packaged}' nor the source '{source}' exists"
    )
