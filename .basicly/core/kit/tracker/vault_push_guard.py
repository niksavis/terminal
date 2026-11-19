from __future__ import annotations

import argparse
import importlib
import importlib.util
import math
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NamedTuple

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / (name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError("The vault push guard is incomplete. Reinstall tracker protection.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


git_runner = _load("git_runner")
MAIN = "refs/heads/main"
MAX_INPUT = 1 << 20
_EVENT_ID = re.compile(r"(?:[0-9a-f]{32}|[0-9a-f]{64})")
_SEGMENT = re.compile(r"log/[0-9a-f]{32}/[0-9]+\.jsonl")
KINDS = frozenset({
    "claim",
    "claim-lost",
    "take",
    "unassign",
    "status",
    "config",
    "comment",
    "ended",
    "ledger",
    "miss",
    "link",
    "requeue",
})


class PushRefusedError(ValueError):
    pass


class Update(NamedTuple):
    new: str
    old: str


def updates(text: str) -> list[Update]:
    if len(text.encode("utf-8")) > MAX_INPUT:
        raise PushRefusedError("The push request is too large. Push only the vault main branch.")
    result = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 4:
            raise PushRefusedError("Malformed push input. Run protection through Git pre-push.")
        _local, new, remote, old = parts
        if remote != MAIN or result:
            raise PushRefusedError("Only refs/heads/main may be pushed to this vault.")
        try:
            git_runner.commit_id(new)
            git_runner.commit_id(old)
        except git_runner.GitValueError as exc:
            raise PushRefusedError(
                "A push object id is invalid. Let Git supply the pre-push input."
            ) from exc
        if len(new) != len(old):
            raise PushRefusedError(
                "The push mixes object formats. Fetch the vault before retrying."
            )
        if set(new) == {"0"}:
            raise PushRefusedError("Vault branch deletion is refused. Preserve its history.")
        result.append(Update(new, old))
    return result


def _git(repository: Path, *args: str) -> str:
    return git_runner.run(list(args), repository)


def _path(path: str) -> bool:
    if path in _load("vault_shapes").GENESIS_FILES or _SEGMENT.fullmatch(path):
        return True
    parts = path.split("/")
    return (
        path.startswith("log/archive/")
        and path.endswith(".jsonl")
        and all(part not in {"", ".", ".."} for part in parts)
    )


def _tree(repository: Path, tip: str) -> None:
    tree = _git(repository, "ls-tree", "-r", "-z", "--full-tree", tip)
    for entry in tree.split("\0"):
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, _object = metadata.split()
        if mode != "100644" or kind != "blob" or not _path(path):
            raise PushRefusedError(
                "A commit contains unexpected vault files or file modes. "
                "Preserve the clone and inspect it."
            )


def _ledger(body: object, record: str) -> None:
    if not isinstance(body, dict):
        raise PushRefusedError(
            "A vault ledger event lacks its record data. Preserve the queue and inspect it."
        )
    codec = _load("events")
    json = importlib.import_module("json")
    try:
        carried = codec.from_json(json.dumps(body))
        codec.accumulate(codec.Totals(), carried.kind, carried.payload)
    except codec.InvalidEventError as exc:
        raise PushRefusedError(
            "A carried ledger event is invalid. Preserve the queue and inspect its record data."
        ) from exc
    if carried.record != record:
        raise PushRefusedError(
            "A carried ledger event names another record. Preserve the queue and inspect it."
        )


def _event(event: Mapping[str, Any]) -> None:
    identity = event.get("id")
    if not isinstance(identity, str) or not _EVENT_ID.fullmatch(identity):
        raise PushRefusedError(
            "A vault event has no valid event id. Preserve the queue and inspect it."
        )
    if not isinstance(event.get("kind"), str) or event["kind"] not in KINDS:
        raise PushRefusedError(
            "A vault event has an unsupported kind. Update the tracker before retrying."
        )
    git_runner.writer_id(event.get("writer"))
    at = event.get("at")
    if type(at) not in (int, float) or (isinstance(at, float) and not math.isfinite(at)):
        raise PushRefusedError(
            "A vault event has an invalid timestamp. Preserve the queue and inspect it."
        )
    global_kind = event["kind"] in {"config", "ended", "requeue"}
    record = event.get("record", "" if global_kind else None)
    if not isinstance(event.get("session"), str) or not isinstance(record, str):
        raise PushRefusedError(
            "A vault event lacks its session or record. Preserve the queue and inspect it."
        )
    if event["kind"] in {"claim", "take", "unassign"} and not event["session"]:
        raise PushRefusedError(
            "An ownership event has no session. Name the session before claiming or releasing."
        )
    if event["kind"] == "ledger":
        _ledger(event.get("ledger"), record)
    if "payload" in event and not isinstance(event["payload"], dict):
        raise PushRefusedError(
            "A vault event has invalid payload data. Preserve the queue and inspect it."
        )


def _commits(repository: Path, update: Update) -> list[str]:
    first = set(update.old) == {"0"}
    if not first:
        try:
            _git(repository, "merge-base", "--is-ancestor", update.old, update.new)
        except git_runner.GitCommandError as exc:
            raise PushRefusedError(
                "Vault history rewrite is refused. Fetch the vault before retrying."
            ) from exc
    _git(repository, "cat-file", "-e", update.new + "^{commit}")
    selected = update.new if first else update.old + ".." + update.new
    return _git(repository, "rev-list", "--reverse", selected).splitlines()


def check(repository: Path, text: str) -> dict[str, int]:
    proposed = updates(text)
    count = 0
    for update in proposed:
        for commit in _commits(repository, update):
            shapes = _load("vault_shapes")
            verdict = shapes.classify(repository, commit)
            if not verdict.valid:
                raise PushRefusedError(
                    "An outgoing commit violates the vault format. "
                    "Preserve the clone and inspect its history."
                )
            if verdict.shape == shapes.FORMAT:
                raise PushRefusedError(
                    "Vault format changes require reviewed tracker maintenance. "
                    "Preserve the proposed commit."
                )
            _tree(repository, commit)
            for event in verdict.events:
                _event(event)
            count += 1
    return {"updates": len(proposed), "commits": count}


def remote_location(value: str, root: Path) -> str:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    if candidate.is_dir():
        return candidate.resolve().as_uri()
    return git_runner.remote_url(value, allow_file=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a protected vault push before publication.")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--origin-root", type=Path, required=True)
    parser.add_argument("--expected-remote", required=True)
    parser.add_argument("remote_name")
    parser.add_argument("remote_location")
    args = parser.parse_args(argv)
    try:
        expected = remote_location(args.expected_remote, args.origin_root)
        if remote_location(args.remote_location, args.origin_root) != expected:
            raise PushRefusedError(
                "The push targets another repository. Use the vault's configured remote."
            )
        check(args.repository, sys.stdin.read(MAX_INPUT + 1))
    except (ValueError, OSError, git_runner.GitRunnerError) as exc:
        sys.stderr.write(f"vault-push: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
