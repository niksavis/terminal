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

from collections.abc import Iterator
from pathlib import Path

CATALOG_DIRNAME = "catalog"


def bundled_catalog_root() -> Path:
    """Return the root of the catalog bundled with this package.

    A source checkout or editable install resolves to the live authoring source
    ``.basicly/core`` — found by walking up from this file to the directory that
    contains ``src/basicly/catalog.py`` (a marker for the basicly source tree
    itself, not a fixed directory depth) — so a stale projected copy can never
    shadow it. An installed wheel has no such ancestor and resolves to the
    packaged copy at ``basicly/catalog``.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "src" / "basicly" / "catalog.py").is_file():
            source = parent / ".basicly" / "core"
            if source.is_dir():
                return source

    packaged = here.parent / CATALOG_DIRNAME
    if packaged.is_dir():
        return packaged

    raise FileNotFoundError(
        f"bundled catalog not found: no basicly source checkout above {here} "
        f"and no packaged copy at '{packaged}'"
    )


def iter_catalog_files(src: Path) -> Iterator[Path]:
    """Yield the catalog files under ``src``, skipping Python bytecode caches.

    The single definition of "what counts as a catalog file" — used by both
    ``init`` materialization and the hooks projection so their file sets can
    never drift apart.
    """
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        yield path
