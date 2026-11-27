from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "basicly.tracker.frozen-ledger.v1"
LEDGER = Path(".basicly/ledger")
ARCHIVE = "ledger-archive"
_DIGEST = re.compile(r"[0-9a-f]{64}")


class FreezeError(ValueError):
    exit_code = 2


def _load(sibling: str) -> Any:
    home = str(Path(__file__).resolve().parent)
    name = "basicly_tracker_freeze_" + sibling + "_" + _hash(home)[:16]
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(sibling + ".py"))
    if spec is None or spec.loader is None:
        raise FreezeError(sibling + ".py is missing beside the tracker; reinstall the kit")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def fingerprint(directory: Path) -> dict[str, str]:
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise FreezeError("the source ledger must be a real directory before freezing")
    found = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise FreezeError("a ledger archive must not contain symbolic links")
    paths = _load("ledger_files").ledger_paths(directory)
    template = directory / "template.json"
    if template.is_file():
        paths.append(template)
    for path in paths:
        if not path.is_file():
            raise FreezeError("ledger event paths must be regular files")
        found[path.relative_to(directory).as_posix()] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    return found


def _marker(directory: Path) -> dict[str, Any]:
    if directory.is_symlink():
        raise FreezeError("the moved ledger file must not be a symbolic link")
    try:
        value = json.loads(directory.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FreezeError(
            "the ledger file is not a valid moved marker; inspect the saved archive"
        ) from exc
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "archive", "prefix", "vault_digest", "files", "notice"}
        or value["schema"] != SCHEMA
        or value["archive"] != ARCHIVE
        or not isinstance(value["prefix"], str)
        or not isinstance(value["vault_digest"], str)
        or not _DIGEST.fullmatch(value["vault_digest"])
        or not isinstance(value["files"], dict)
        or not isinstance(value["notice"], str)
    ):
        raise FreezeError("the moved ledger marker is malformed; inspect the saved archive")
    for name, digest in value["files"].items():
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or not isinstance(digest, str)
            or not _DIGEST.fullmatch(digest)
        ):
            raise FreezeError("the moved ledger marker contains an invalid archive fingerprint")
    return value


def check(directory: Path) -> Path | None:
    archive = directory.with_name(ARCHIVE)
    if not directory.is_file():
        if archive.exists():
            raise FreezeError(
                "a ledger archive exists without its moved file; inspect interrupted migration"
            )
        return None
    marker = _marker(directory)
    if not archive.is_dir() or archive.is_symlink():
        raise FreezeError(
            "the moved ledger archive is missing or unsafe; restore the complete saved archive"
        )
    config = _load("vault_config").load(directory.parent.parent)
    if (
        config is None
        or config.prefix != marker["prefix"]
        or _hash(config.vault) != marker["vault_digest"]
    ):
        raise FreezeError(
            "the moved ledger and vault configuration differ; restore the verified configuration"
        )
    if fingerprint(archive) != marker["files"]:
        raise FreezeError(
            "the archived ledger changed outside the vault; "
            "stop old writers and reconcile the extra history"
        )
    return archive


@contextmanager
def _transition(directory: Path) -> Iterator[None]:
    lock = directory.parent / "ledger-freeze.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise FreezeError(
            "another ledger freeze holds the transition lock; finish it before retrying"
        ) from None
    try:
        yield
    finally:
        handle.close()
        lock.unlink()


@contextmanager
def _source_lock(directory: Path) -> Iterator[bool]:
    source = directory if directory.is_dir() else directory.with_name(ARCHIVE)
    if not source.exists():
        if directory.exists():
            raise FreezeError(
                "the moved ledger archive is missing; preserve the marker and restore it"
            )
        yield False
        return
    backend = _load("locking")
    lock = source / backend.LEDGER_LOCK_NAME
    if lock.is_symlink():
        raise FreezeError("the source ledger lock must not be a symbolic link")
    try:
        handle = backend.open_movable(lock)
    except OSError as exc:
        raise FreezeError(
            "the source filesystem cannot lock this ledger safely; use its owning host"
        ) from exc
    try:
        try:
            acquired = backend.try_exclusive(handle)
        except OSError as exc:
            raise FreezeError(
                "the source filesystem cannot lock this ledger safely; use its owning host"
            ) from exc
        if not acquired:
            raise FreezeError(
                "another writer holds the source ledger; finish its write before freezing"
            )
        yield True
    finally:
        os.close(handle)


def source_path(directory: Path) -> None:
    if (
        directory.name != "ledger"
        or directory.parent.name != ".basicly"
        or directory.is_symlink()
        or directory.parent.is_symlink()
    ):
        raise FreezeError(f"freeze the base checkout's ledger; {directory} is redirected or custom")
    if (directory / "redirect").is_file():
        raise FreezeError(
            "freeze the base checkout; a worktree ledger redirect must not be archived"
        )


def freeze(
    directory: Path, vault: str, prefix: str, expected: Mapping[str, str]
) -> dict[str, object]:
    config_module = _load("vault_config")
    vault = config_module.address(vault)
    text = config_module.text(vault, prefix)
    source_path(directory)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with _transition(directory), _source_lock(directory) as locked:
        existing = config_module.load(directory.parent.parent)
        if existing is not None and (existing.vault != vault or existing.prefix != prefix):
            raise FreezeError(
                "the repository already names another vault or prefix; nothing was frozen"
            )
        if directory.is_file():
            archive = check(directory)
            if archive is None or fingerprint(archive) != dict(expected):
                raise FreezeError("the frozen source differs from the verified migration")
            return {
                "frozen": True,
                "archive": str(LEDGER.with_name(ARCHIVE)),
                "files": len(expected),
            }
        archive = directory.with_name(ARCHIVE)
        if directory.exists() and archive.exists():
            raise FreezeError(
                "ledger-archive already exists; preserve both directories and reconcile them"
            )
        source = archive if archive.exists() else directory
        if fingerprint(source) != dict(expected):
            raise FreezeError(
                "the source ledger changed after verification; migrate its new history first"
            )
        marker = {
            "schema": SCHEMA,
            "archive": ARCHIVE,
            "prefix": prefix,
            "vault_digest": _hash(vault),
            "files": dict(expected),
            "notice": (
                "Local history is archived and frozen; "
                "use basicly-tracker status and configured vault commands."
            ),
        }
        try:
            if locked and source == directory and directory.exists():
                _drop_caches(directory)
                directory.rename(archive)
            with directory.open("x", encoding="utf-8") as target:
                target.write(json.dumps(marker, indent=2, sort_keys=True) + "\n")
            if not locked:
                archive.mkdir()
            if not expected and not (archive / ".keep").exists():
                (archive / ".keep").touch(exist_ok=False)
            if existing is None:
                with (directory.parent.parent / config_module.CONFIG_PATH).open(
                    "x", encoding="utf-8"
                ) as target:
                    target.write(text)
            check(directory)
        except OSError as exc:
            raise FreezeError(
                "ledger freeze was interrupted; preserve ledger-archive and inspect both paths"
            ) from exc
    _drop_lock(directory.with_name(ARCHIVE))
    return {"frozen": True, "archive": str(LEDGER.with_name(ARCHIVE)), "files": len(expected)}


def _drop_caches(directory: Path) -> None:
    snapshot = _load("snapshot")
    for path in (snapshot.snapshot_path(directory), *snapshot.checkpoint_paths(directory)):
        if path.is_file() and not path.is_symlink():
            path.unlink()


def _drop_lock(archive: Path) -> None:
    lock = archive / _load("locking").LEDGER_LOCK_NAME
    if lock.is_file() and not lock.is_symlink():
        lock.unlink(missing_ok=True)


def check_source(directory: Path) -> Path | None:
    local = directory.with_name(LEDGER.name) if directory.name == ARCHIVE else directory
    if local.name == LEDGER.name and local.parent.name == LEDGER.parent.name:
        return check(local)
    return None


def refuse_local_fsck(directory: Path) -> None:
    if not directory.is_file():
        return
    check(directory)
    config = _load("vault_config").load(directory.parent.parent)
    vault = config.vault if config is not None else "URL"
    raise FreezeError(
        f"{directory.as_posix()} is the frozen guard file of a vault consumer, so its records "
        f"live in the vault; run `python3 .basicly/core/kit/tracker/cli.py fsck --vault {vault}`"
    )


def refuse_append(directory: Path) -> None:
    check_source(directory)
    if directory.is_file():
        check(directory)
        raise FreezeError(
            "the local ledger is frozen; use basicly-tracker status and configured vault commands"
        )
    config = _load("vault_config").load(directory)
    if config is None:
        return
    local = config.path.parent / LEDGER
    if directory.resolve() in {local.resolve(), local.with_name(ARCHIVE).resolve()}:
        if local.is_file():
            check(local)
        raise FreezeError(
            "local ledger appends bypass the configured vault; use the vault tracker commands"
        )
