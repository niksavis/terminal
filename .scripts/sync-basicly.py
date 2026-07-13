"""Sync the vendored basicly engine and core catalog from the basicly repository.

Until basicly ships as a uvx-installable package, this repo vendors the engine
at .basicly/basicly/ and the managed core catalog at .basicly/core/. This
script is the only supported way to refresh them: it copies both trees from a
basicly source checkout, applies this repo's skill exclusions, records the
source commit in .basicly/README.md, and regenerates the projected files.

Usage: uv run python .scripts/sync-basicly.py [--source PATH] [--skip-build]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

ENGINE_SUBDIR = Path("src/basicly")
CATALOG_SUBDIR = Path(".basicly/core")
VENDORED_ENGINE = PROJECT_ROOT / ".basicly" / "basicly"
VENDORED_CATALOG = PROJECT_ROOT / ".basicly" / "core"
PROVENANCE_README = PROJECT_ROOT / ".basicly" / "README.md"

# Catalog skills that mandate a beads issue-tracker commit workflow this repo
# does not use; excluded until basicly supports per-consumer catalog selection.
EXCLUDED_SKILLS = ("conventional-commits", "tool-br")
SKILL_PROJECTION_ROOTS = (
    PROJECT_ROOT / ".claude" / "skills",
    PROJECT_ROOT / ".github" / "skills",
    PROJECT_ROOT / ".agents" / "skills",
)

COMMIT_HASH_PATTERN = re.compile(r"`[0-9a-f]{40}`")


def copy_tree_filtered(src: Path, dst: Path) -> int:
    """Replace dst with a copy of src, skipping Python bytecode caches.

    Returns the number of files copied.
    """
    if dst.exists():
        shutil.rmtree(dst)

    copied = 0
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        target = dst / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


def remove_excluded_skills(catalog_dir: Path, projection_roots: tuple[Path, ...]) -> list[Path]:
    """Delete excluded skills from the catalog and any projected copies.

    Returns the paths that were removed.
    """
    removed: list[Path] = []
    roots = (catalog_dir / "skills", *projection_roots)
    for root in roots:
        for slug in EXCLUDED_SKILLS:
            skill_dir = root / slug
            if skill_dir.exists():
                shutil.rmtree(skill_dir)
                removed.append(skill_dir)
    return removed


def update_provenance_text(readme_text: str, commit: str) -> str:
    """Replace the recorded source commit hash in the provenance README text."""
    return COMMIT_HASH_PATTERN.sub(f"`{commit}`", readme_text, count=1)


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(  # nosec
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _run_engine(command: str) -> int:
    print(f"==> basicly {command}")
    env = os.environ.copy()
    env["PYTHONPATH"] = ".basicly"
    result = subprocess.run(  # nosec
        ["uv", "run", "python", "-m", "basicly.cli", command],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    return result.returncode


def main() -> int:
    """Entry point for the sync script."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT_ROOT.parent / "basicly",
        help="Path to a basicly source checkout (default: sibling 'basicly' directory)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Sync files only; do not regenerate projected outputs",
    )
    args = parser.parse_args()

    source: Path = args.source.resolve()
    engine_src = source / ENGINE_SUBDIR
    catalog_src = source / CATALOG_SUBDIR
    if not engine_src.is_dir() or not catalog_src.is_dir():
        print(
            f"Source '{source}' does not look like a basicly checkout "
            f"(missing {ENGINE_SUBDIR} or {CATALOG_SUBDIR}).",
            file=sys.stderr,
        )
        return 1

    dirty = _git_output(source, "status", "--porcelain", "--", "src", ".basicly/core")
    if dirty:
        print(
            "Warning: source repo has uncommitted engine/catalog changes; "
            "the recorded commit will not describe what was copied.",
            file=sys.stderr,
        )

    commit = _git_output(source, "rev-parse", "HEAD")

    engine_count = copy_tree_filtered(engine_src, VENDORED_ENGINE)
    catalog_count = copy_tree_filtered(catalog_src, VENDORED_CATALOG)
    removed = remove_excluded_skills(VENDORED_CATALOG, SKILL_PROJECTION_ROOTS)

    readme_text = PROVENANCE_README.read_text(encoding="utf-8")
    updated_text = update_provenance_text(readme_text, commit)
    if updated_text != readme_text:
        PROVENANCE_README.write_text(updated_text, encoding="utf-8")

    print(f"Synced engine ({engine_count} files) and catalog ({catalog_count} files).")
    for path in removed:
        print(f"Removed excluded skill: {path.relative_to(PROJECT_ROOT)}")
    print(f"Recorded source commit {commit}")

    if args.skip_build:
        print("Skipped build; run `PYTHONPATH=.basicly uv run python -m basicly.cli build`.")
        return 0

    for command in ("build", "skills-build", "check", "skills-check"):
        code = _run_engine(command)
        if code != 0:
            print(f"basicly {command} failed with exit code {code}", file=sys.stderr)
            return code

    print("Sync complete; generated files are up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
