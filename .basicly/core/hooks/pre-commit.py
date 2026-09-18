from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import apply_fixes, project_root, run_checks


def main() -> int:
    repo_root = project_root()
    apply_fixes(repo_root, "fast")
    return run_checks(repo_root, "fast", scope_to_diff=True)


if __name__ == "__main__":
    sys.exit(main())
