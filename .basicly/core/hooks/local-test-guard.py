from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_runs import ALLOWED, changed_files, refusal

BLOCK_EXIT_CODE = 2


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError, ValueError:
        return 0
    if not isinstance(payload, dict) or str(payload.get("tool_name", "")).lower() != "bash":
        return 0
    args = payload.get("tool_input") or {}
    command = args.get("command") if isinstance(args, dict) else None
    if not isinstance(command, str):
        return 0
    found = refusal(command, changed_files(Path(str(payload.get("cwd") or "."))))
    if found:
        print(
            f"local-test-guard: refusing {found}. Local runs stay small: {ALLOWED}", file=sys.stderr
        )
        return BLOCK_EXIT_CODE
    return 0


if __name__ == "__main__":
    sys.exit(main())
