"""Cross-platform terminal environment setup automation."""

from __future__ import annotations

# Kept in step with [project] version in pyproject.toml by
# tests/test_version.py. Deriving it from installed metadata instead does not
# work here: `[tool.uv] package = false`, so a dev checkout and CI have no
# installed distribution to read and would report a placeholder.
__version__ = "0.5.1"
