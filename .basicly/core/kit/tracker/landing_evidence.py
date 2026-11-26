from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


FIELD = "landing_evidence"
ARTIFACT = "landing-verification"
VERIFIED = "ci-verified"
TYPES = ("task", "bug", "chore")
_SHA = re.compile(r"^[0-9a-f]{40}$")

Runner = Callable[[Sequence[str], Path], str]


class LandingEvidenceError(ValueError):
    pass


def _git(args: Sequence[str], cwd: Path) -> str:
    git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")
    try:
        return git_runner.run(list(args), cwd)
    except git_runner.GitRunnerError as exc:
        raise LandingEvidenceError(f"git {args[0]} refused: {exc}") from None


def applies(fields: Mapping[str, object]) -> bool:
    return fields.get("issue_type") in TYPES


def _verified(artifact: object, commit: str) -> bool:
    return (
        isinstance(artifact, Mapping)
        and artifact.get("status") == VERIFIED
        and artifact.get("head") == commit
        and isinstance(artifact.get("run"), str)
        and bool(artifact.get("run"))
    )


def gather(
    root: Path,
    commit: str,
    artifact: object,
    tests: Mapping[str, object],
    criteria: Sequence[str],
) -> dict[str, object]:
    run = _git
    try:
        full = run(["rev-parse", "--verify", f"{commit}^{{commit}}"], root).strip()
    except LandingEvidenceError:
        raise LandingEvidenceError(
            f"{commit!r} names no commit in this repository; pass the merge commit that "
            "basicly worktree merge printed"
        ) from None
    if not _verified(artifact, full):
        raise LandingEvidenceError(
            f"the record has no {ARTIFACT} artifact for {full[:12]}: land it with "
            "basicly worktree merge --mode ci, which proves CI on the exact head, then close it"
        )
    run(["merge-base", "--is-ancestor", full, "origin/HEAD"], root)
    mapped = _mapped(tests, criteria)
    for path in sorted({p for p in mapped.values() if p}):
        try:
            run(["cat-file", "-e", f"{full}:{path}"], root)
        except LandingEvidenceError:
            raise LandingEvidenceError(f"{path} is not in commit {full[:12]}") from None
    verified: Mapping[str, object] = artifact if isinstance(artifact, Mapping) else {}
    return {"commit": full, "run": str(verified.get("run", "")), "tests": mapped}


def _mapped(tests: Mapping[str, object], criteria: Sequence[str]) -> dict[str, str | None]:
    if not criteria:
        raise LandingEvidenceError("the record has no acceptance criteria to map to tests")
    keys = set(tests)
    wanted = set(criteria)
    if keys != wanted:
        missing = sorted(wanted - keys)
        extra = sorted(keys - wanted)
        raise LandingEvidenceError(
            "--tests must map each acceptance criterion exactly; "
            f"missing: {missing}; not a criterion: {extra}"
        )
    for key, value in tests.items():
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise LandingEvidenceError(f"the test for {key!r} must be a file path or null")
    return {
        key: (value.strip() if isinstance(value, str) else None) for key, value in tests.items()
    }


def parsed(value: object) -> Mapping[str, object]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, Mapping) else {}


def complete(
    fields: Mapping[str, object], criteria: Sequence[str], artifacts: Mapping[str, object]
) -> bool:
    value = parsed(fields.get(FIELD))
    tests = value.get("tests")
    commit = str(value.get("commit", ""))
    return (
        applies(fields)
        and bool(criteria)
        and bool(_SHA.match(commit))
        and _verified(artifacts.get(ARTIFACT), commit)
        and isinstance(tests, Mapping)
        and set(tests) == set(criteria)
    )


def untested(value: object) -> list[str]:
    tests = parsed(value).get("tests")
    return sorted(k for k, v in tests.items() if v is None) if isinstance(tests, Mapping) else []
