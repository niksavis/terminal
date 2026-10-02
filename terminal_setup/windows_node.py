from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import Path

from .release_install import InstallError, fetch, verified

NODE_DIST = "https://nodejs.org/dist"
WINDOWS_ARCHES = {"AMD64": "x64", "x86_64": "x64", "ARM64": "arm64", "aarch64": "arm64"}
STALE_SUFFIX = ".old"


def latest_version(major: str) -> str:
    for entry in json.loads(fetch(f"{NODE_DIST}/index.json")):
        version = entry.get("version", "")
        if version.startswith(f"v{major}."):
            return version
    raise InstallError(f"nodejs.org lists no Node.js v{major} release")


def archive_name(version: str, machine: str) -> str:
    arch = WINDOWS_ARCHES.get(machine)
    if arch is None:
        raise InstallError(f"no Node.js Windows build for this CPU ({machine})")
    return f"node-{version}-win-{arch}.zip"


def published_digest(sums: str, name: str) -> str:
    for line in sums.splitlines():
        digest, _, file = line.strip().partition("  ")
        if file == name:
            return f"sha256:{digest}"
    raise InstallError(f"SHASUMS256.txt lists no checksum for {name}")


def remove_stale(target: Path) -> None:
    for stale in target.rglob(f".*{STALE_SUFFIX}"):
        try:
            stale.unlink()
        except PermissionError:
            continue


def replace_file(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=f".{destination.name}.")
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
    try:
        Path(temporary).replace(destination)
    except PermissionError:
        destination.rename(
            destination.with_name(f".{destination.name}.{uuid.uuid4().hex}{STALE_SUFFIX}")
        )
        Path(temporary).replace(destination)


def extract_into(payload: bytes, root: str, target: Path) -> int:
    resolved_target = target.resolve()
    count = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.startswith(root):
                continue
            destination = target / member.filename[len(root) :]
            if not destination.resolve().is_relative_to(resolved_target):
                raise InstallError(f"the archive entry {member.filename} leaves {target}")
            replace_file(destination, archive.read(member))
            count += 1
    if count == 0:
        raise InstallError(f"the archive holds no files under {root}")
    return count


def install(version: str, machine: str, target: Path) -> None:
    name = archive_name(version, machine)
    digest = published_digest(fetch(f"{NODE_DIST}/{version}/SHASUMS256.txt").decode(), name)
    payload = verified(fetch(f"{NODE_DIST}/{version}/{name}"), digest)
    target.mkdir(parents=True, exist_ok=True)
    remove_stale(target)
    extract_into(payload, f"{name.removesuffix('.zip')}/", target)
