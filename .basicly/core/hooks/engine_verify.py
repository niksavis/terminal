from __future__ import annotations

import importlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import load_checks, load_fail_fast, project_root


def cache_savings(root: Path) -> float:
    path = root / ".basicly/usage/verify-cache.json"
    try:
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()) or any(
            part.startswith(".env") for part in resolved.relative_to(root.resolve()).parts
        ):
            return 0
        with path.open("rb") as stream:
            content = stream.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            return 0
        payload = json.loads(content)
        checks = payload.get("checks") if isinstance(payload, dict) else None
        if not isinstance(checks, list) or len(checks) > 128:
            return 0
        overhead = payload["overhead_s"]
        durations = [entry["duration_s"] for entry in checks]
        if any(
            type(value) not in {int, float} or not math.isfinite(value) or value < 0
            for value in [overhead, *durations]
        ):
            return 0
        return max(0, sum(durations) - overhead)
    except OSError, ValueError, TypeError, KeyError:
        return 0


def main() -> int:
    try:
        config = importlib.import_module("basicly.config")
        verify = importlib.import_module("basicly.verify")
    except ModuleNotFoundError as exc:
        if exc.name == "basicly":
            return 125
        raise
    root = project_root()
    settings = config.load_verify_config(root)
    inventory = [(check.name, list(check.command)) for check in settings.for_mode("full")]
    if (
        not settings.cache
        or inventory != load_checks(root, "full")
        or settings.fail_fast != load_fail_fast(root)
    ):
        return 125
    report = verify.run_verify(root, "full", settings)
    print(f"pre-push: engine full verification {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
