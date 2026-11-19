from __future__ import annotations

import os


def environment_without_git() -> dict[str, str]:
    return {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
