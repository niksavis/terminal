#!/usr/bin/env python3
"""Convenience entry point for the terminal setup."""

from __future__ import annotations

import sys
from pathlib import Path

# Add the package directory to the path so this script can be run standalone.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from terminal_setup.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
