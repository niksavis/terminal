from __future__ import annotations

import importlib.util
import sys
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _scan():
    cached = sys.modules.get("basicly_comments_kit_scan")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location("basicly_comments_kit_scan", _HERE / "scan.py")
    if spec is None or spec.loader is None:
        raise ImportError("the comments kit's scan.py is missing from beside ratchet.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compare(path: Path, before: str, after: str, previous: Path) -> list:
    scan = _scan()
    legacy = (
        Counter(finding.text for finding in scan.findings(previous, before))
        if scan.is_covered(previous)
        else Counter()
    )
    added = []
    for finding in scan.findings(path, after):
        if legacy[finding.text]:
            legacy[finding.text] -= 1
        else:
            added.append(finding)
    return added
