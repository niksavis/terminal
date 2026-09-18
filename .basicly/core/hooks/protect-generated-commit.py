from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

MANIFEST_BASENAME = "generated-manifest.json"
MANIFEST_DEFAULT = Path(".basicly") / MANIFEST_BASENAME

BLOCK_EXIT_CODE = 1


def find_manifest(root: Path) -> Path | None:
    default = root / MANIFEST_DEFAULT
    if default.is_file():
        return default
    marker_root = root / ".basicly"
    if marker_root.is_dir():
        for candidate in sorted(marker_root.rglob(MANIFEST_BASENAME)):
            if candidate.is_file():
                return candidate
    return None


def manifest_hashes(manifest_path: Path) -> dict[str, str]:
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    outputs = data.get("outputs") if isinstance(data, dict) else None
    if not isinstance(outputs, dict):
        return {}
    return {
        rel: entry["hash"]
        for rel, entry in outputs.items()
        if isinstance(entry, dict) and isinstance(entry.get("hash"), str)
    }


def hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], capture_output=True, check=False)  # nosec B603 B607


def staged_paths() -> list[str]:
    proc = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"])
    if proc.returncode != 0:
        return []
    return [part for part in proc.stdout.decode("utf-8", errors="ignore").split("\0") if part]


def staged_blob(path: str) -> bytes | None:
    proc = _git(["show", f":{path}"])
    if proc.returncode != 0:
        return None
    return proc.stdout


def violations(
    hashes: dict[str, str], staged: list[str], blob_of: Callable[[str], bytes | None]
) -> list[str]:
    bad = []
    for path in staged:
        expected = hashes.get(path)
        if expected is None:
            continue
        blob = blob_of(path)
        if blob is None:
            continue
        if hash_bytes(blob) != expected:
            bad.append(path)
    return bad


def main() -> int:
    manifest = find_manifest(Path.cwd())
    if manifest is None:
        return 0
    hashes = manifest_hashes(manifest)
    if not hashes:
        return 0
    bad = violations(hashes, staged_paths(), staged_blob)
    if not bad:
        return 0
    print(
        "BLOCKED: staged edit to basicly-generated file(s) that no longer match the "
        "projection manifest:",
        file=sys.stderr,
    )
    for path in bad:
        print(f"  - {path}", file=sys.stderr)
    print(
        "These files are generated. Edit the catalog source (fragment/skill/agent YAML "
        "under .basicly/core or the .basicly-local overlay), run `basicly build` to "
        "regenerate them, and stage the result (see docs/architecture/architecture.md §11).",
        file=sys.stderr,
    )
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
