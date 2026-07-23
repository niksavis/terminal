"""Block a commit that stages a hand-edited basicly-generated file (git backstop).

Companion to ``protect-generated.py``: that PreToolUse guard fails open and is
Claude-specific, so a tool-time bypass — or any other agent — can still stage an
edit to a generated file and reach a commit. This pre-commit hook is the
deterministic, agent-independent backstop (basicly-yw28).

It reads the projection manifest (``generated-manifest.json`` -> ``outputs``, a
map of repo-relative path to the sha256 the last ``basicly build`` recorded) and,
for every staged generated OUTPUT whose staged blob no longer matches that hash,
blocks the commit. A legitimate rebuild stages the regenerated file AND the
updated manifest together, so their hashes agree and the commit passes; a
hand-edit that skips the rebuild does not, and is caught here.

Read-only and precise: it hashes the staged blob (the exact bytes being
committed) against the manifest, touches nothing, and only fails on a real
mismatch. A missing manifest or an unreadable git index exits 0 (fail-safe: this
is a guardrail against accidents, not a security boundary — the same stance as
the PreToolUse guard).
"""

from __future__ import annotations

import hashlib
import json
import subprocess  # nosec B404
import sys
from collections.abc import Callable
from pathlib import Path

# The projection manifest is JSON (no comment marker); its basename is constant
# though its directory is configurable, so it is located by name under .basicly.
MANIFEST_BASENAME = "generated-manifest.json"
MANIFEST_DEFAULT = Path(".basicly") / MANIFEST_BASENAME

BLOCK_EXIT_CODE = 1


def find_manifest(root: Path) -> Path | None:
    """Locate the projection manifest under *root* (default path first, then search)."""
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
    """Map each generated output path to its recorded sha256 (empty on any error)."""
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
    """The manifest's hash form for *data* (mirrors renderers.common.sha256_of_text)."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _git(args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], capture_output=True, check=False)  # nosec B603 B607


def staged_paths() -> list[str]:
    """Repo-relative paths staged as Added/Copied/Modified (index has content)."""
    proc = _git(["diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"])
    if proc.returncode != 0:
        return []
    return [part for part in proc.stdout.decode("utf-8", errors="ignore").split("\0") if part]


def staged_blob(path: str) -> bytes | None:
    """The staged (index) content of *path*, or None when it cannot be read."""
    proc = _git(["show", f":{path}"])
    if proc.returncode != 0:
        return None
    return proc.stdout


def violations(
    hashes: dict[str, str], staged: list[str], blob_of: Callable[[str], bytes | None]
) -> list[str]:
    """Staged generated files whose staged content diverges from the manifest hash."""
    bad = []
    for path in staged:
        expected = hashes.get(path)
        if expected is None:
            continue
        blob = blob_of(path)
        if blob is None:  # deleted from the index or unreadable — not an edit to catch
            continue
        if hash_bytes(blob) != expected:
            bad.append(path)
    return bad


def main() -> int:
    """Fail the commit when a staged generated file no longer matches the manifest."""
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
        "regenerate them, and stage the result (see docs/architecture.md §3.4).",
        file=sys.stderr,
    )
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
