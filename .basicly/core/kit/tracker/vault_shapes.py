from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_shapes.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner.py", "basicly_tracker_kit_git_runner")

GENESIS_FILES = frozenset({"vault.toml", "FORMAT.md", "reader.py", "README.md"})
FORMAT_FILES = frozenset({"FORMAT.md", "reader.py", "README.md"})
LOG_ROOT = "log"
ARCHIVE = "archive"
SEGMENT_KIND = "segment"
STOP_KIND = "ended"

GENESIS = "genesis"
FORMAT = "format"
BATCH = "batch"
ARCHIVED = "archive"
QUARANTINED = "quarantined"
AFTER_STOP = "after-ended"

_ZERO = "0" * 40


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    old: str
    new: str


@dataclass(frozen=True)
class Verdict:
    commit: str
    shape: str
    rule: str = ""
    events: tuple = ()

    @property
    def valid(self) -> bool:
        return self.shape not in (QUARANTINED, AFTER_STOP)


class ShapeError(ValueError):
    pass


def _git(vault: Path, *args: str) -> str:
    return git_runner.run(list(args), vault)


def first_parent_chain(vault: Path, ref: str = "HEAD") -> list[str]:

    return list(first_parent_entries(vault, ref))


def first_parent_entries(vault: Path, ref: str = "HEAD") -> dict[str, list[str]]:

    if not ref or ref.startswith("-"):
        raise ShapeError(f"refused ref {ref!r}: name a branch or commit")
    out = _git(
        vault,
        "rev-list",
        "--first-parent",
        "--reverse",
        "--parents",
        git_runner.END_OF_OPTIONS,
        ref,
    )
    return {fields[0]: fields[1:] for line in out.splitlines() if (fields := line.split())}


def _parents(vault: Path, commit: str) -> list[str]:
    return _git(vault, "rev-list", "--parents", "-n", "1", commit).split()[1:]


def _changes(vault: Path, commit: str, parent: str | None) -> list[Change]:

    base = [parent, commit] if parent else ["--root", commit]
    raw = _git(vault, "diff-tree", "-r", "--no-renames", "--no-commit-id", "--raw", "-z", *base)
    fields = raw.split("\0")
    changes = []
    for index in range(0, len(fields) - 1, 2):
        meta = fields[index].lstrip(":").split()
        if len(meta) < 5:
            continue
        changes.append(Change(meta[4][0], fields[index + 1], meta[2], meta[3]))
    return changes


def _blob(vault: Path, sha: str) -> str:
    return "" if sha == _ZERO else _git(vault, "cat-file", "blob", sha)


def _segment_owner(path: str) -> str | None:

    parts = path.split("/")
    if len(parts) != 3 or parts[0] != LOG_ROOT or parts[1] == ARCHIVE:
        return None
    return parts[1]


def _lines(text: str, rule: str) -> list[dict]:

    if text and not text.endswith("\n"):
        raise ShapeError(f"{rule}: a line was left without its newline")
    parsed = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            raise ShapeError(f"{rule}: a line is not JSON") from None
        if not isinstance(value, dict):
            raise ShapeError(f"{rule}: a line is not a JSON object")
        parsed.append(value)
    return parsed


def _batch_events(vault: Path, changes: list[Change]) -> tuple:

    owners = {_segment_owner(change.path) for change in changes}
    if None in owners or len(owners) != 1:
        raise ShapeError("batch: a batch appends to one writer's segments under log/ only")
    writer = next(iter(owners))
    try:
        git_runner.writer_id(str(writer))
    except git_runner.GitValueError:
        raise ShapeError("batch: the segment folder is not a writer id") from None
    found: list[dict] = []
    for change in sorted(changes, key=lambda item: item.path):
        if change.status not in ("A", "M"):
            raise ShapeError("batch: a batch never deletes or renames a segment")
        old = _blob(vault, change.old)
        new = _blob(vault, change.new)
        if not new.startswith(old):
            raise ShapeError("batch: an existing line was changed or removed")
        lines = _lines(new[len(old) :], "batch")
        if change.status == "A":
            if (
                not lines
                or lines[0].get("kind") != SEGMENT_KIND
                or lines[0].get("writer") != writer
            ):
                raise ShapeError("batch: a new segment must start with a header naming its writer")
            lines = lines[1:]
        for line in lines:
            if line.get("kind") == SEGMENT_KIND:
                raise ShapeError("batch: a segment header may only open a new segment")
            if line.get("writer") != writer:
                raise ShapeError("batch: a line names a writer other than its segment writer")
        found.extend(lines)
    return tuple(found)


def _is_archive(changes: list[Change]) -> bool:

    gone = sorted(c.old for c in changes if c.status == "D" and _segment_owner(c.path))
    moved = sorted(
        c.new for c in changes if c.status == "A" and c.path.startswith(f"{LOG_ROOT}/{ARCHIVE}/")
    )
    return bool(gone) and len(gone) + len(moved) == len(changes) and gone == moved


def _shape(vault: Path, commit: str, parents: list[str] | None = None) -> Verdict:

    parents = _parents(vault, commit) if parents is None else parents
    if not parents:
        changes = _changes(vault, commit, None)
        added = {c.path for c in changes if c.status == "A"}
        if len(added) != len(changes) or added != GENESIS_FILES:
            raise ShapeError("genesis: it adds exactly vault.toml, FORMAT.md, reader.py, README.md")
        return Verdict(commit, GENESIS)
    if len(parents) > 1:
        raise ShapeError("merge: a vault takes only single-parent commits")
    changes = _changes(vault, commit, parents[0])
    if not changes:
        raise ShapeError("empty: a commit changes nothing")
    if all(c.path in FORMAT_FILES and c.status in ("A", "M") for c in changes):
        return Verdict(commit, FORMAT)
    if _is_archive(changes):
        return Verdict(commit, ARCHIVED)
    return Verdict(commit, BATCH, events=_batch_events(vault, changes))


def classify(vault: Path, commit: str, *, parents: list[str] | None = None) -> Verdict:

    try:
        return _shape(vault, commit, parents)
    except ShapeError as exc:
        return Verdict(commit, QUARANTINED, rule=str(exc))


def check(vault: Path | str, ref: str = "HEAD") -> list[Verdict]:

    root = Path(vault)
    verdicts: list[Verdict] = []
    stopped = False
    for commit in first_parent_chain(root, ref):
        if stopped:
            verdicts.append(
                Verdict(commit, AFTER_STOP, rule="ended: nothing after a valid end counts")
            )
            continue
        verdict = classify(root, commit)
        verdicts.append(verdict)
        stopped = verdict.valid and any(e.get("kind") == STOP_KIND for e in verdict.events)
    return verdicts


def valid_events(verdicts: list[Verdict]) -> list[dict]:
    return [event for verdict in verdicts if verdict.valid for event in verdict.events]


def read(vault: Path | str, ref: str = "HEAD") -> list[Verdict]:

    try:
        return check(vault, ref)
    except git_runner.GitRunnerError as exc:
        raise ShapeError(f"vault-check could not read {vault}: {exc}") from None


def report(vault: Path | str, ref: str = "HEAD") -> dict[str, object]:

    verdicts = read(vault, ref)
    return {
        "valid": sum(1 for verdict in verdicts if verdict.valid),
        "quarantined": [
            {"commit": verdict.commit, "rule": verdict.rule}
            for verdict in verdicts
            if not verdict.valid
        ],
        "commits": [
            {"commit": verdict.commit, "shape": verdict.shape, "rule": verdict.rule}
            for verdict in verdicts
        ],
        "events": len(valid_events(verdicts)),
    }
