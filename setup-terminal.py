#!/usr/bin/env python3
"""Repository-root convenience entry point for terminal setup."""

from __future__ import annotations

import sys

from terminal_setup.cli import main

if __name__ == "__main__":
    sys.exit(main())
