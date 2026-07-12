"""Generate or update a dated changelog section for a semantic release tag."""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
from datetime import date
from pathlib import Path

TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")

CHANGELOG_INTRO = (
    "# Changelog\n\nAll notable user-facing changes are documented in this file by release tag.\n"
)


def _run_git(*args: str) -> str:
    """Run a git command and return stdout or raise on failure."""
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )  # nosec
    if result.returncode != 0:
        message = result.stderr.strip() or f"git {' '.join(args)} failed"
        raise RuntimeError(message)
    return result.stdout.strip()


def _nearest_previous_tag(tag_to_exclude: str) -> str | None:
    """Return the nearest reachable semantic tag, excluding the target release tag."""
    result = subprocess.run(
        [
            "git",
            "describe",
            "--tags",
            "--abbrev=0",
            "--match",
            "v*",
            "--exclude",
            tag_to_exclude,
        ],
        check=False,
        capture_output=True,
        text=True,
    )  # nosec
    if result.returncode != 0:
        return None
    tag = result.stdout.strip()
    return tag or None


def _collect_commit_subjects(previous_tag: str | None) -> list[str]:
    """Collect commit subjects since the previous tag (or all history for first release)."""
    revision = f"{previous_tag}..HEAD" if previous_tag else "HEAD"
    output = _run_git("log", "--no-merges", "--pretty=%s (%h)", revision)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _build_section(
    tag: str,
    release_date: str,
    previous_tag: str | None,
    commits: list[str],
) -> list[str]:
    """Build a markdown changelog section for the target release tag."""
    delta_start = previous_tag or "initial"
    section = [
        f"## {tag} - {release_date}",
        "",
        f"Delta: {delta_start}..{tag}",
        "",
        "### Changes",
    ]
    if commits:
        section.extend([f"- {commit}" for commit in commits])
    else:
        section.append("- No user-visible changes.")
    section.append("")
    return section


def _ensure_changelog_header(lines: list[str]) -> list[str]:
    """Ensure the changelog starts with a standard header and intro text."""
    if not lines:
        return CHANGELOG_INTRO.splitlines()

    if lines[0].strip() == "# Changelog":
        return lines

    return [*CHANGELOG_INTRO.splitlines(), "", *lines]


def _find_section_bounds(lines: list[str], tag: str) -> tuple[int | None, int | None]:
    """Find start and end line indices for a tag section."""
    start: int | None = None
    end: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith(f"## {tag} - "):
            start = idx
            continue
        if start is not None and line.startswith("## "):
            end = idx
            break

    if start is not None and end is None:
        end = len(lines)

    return start, end


def _insert_index(lines: list[str]) -> int:
    """Return where new release sections should be inserted (newest first)."""
    idx = 1
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1
    while idx < len(lines) and not lines[idx].startswith("## "):
        idx += 1
    return idx


def _upsert_section(existing_text: str, tag: str, section_lines: list[str]) -> str:
    """Insert or replace the tag section in the changelog text."""
    lines = _ensure_changelog_header(existing_text.splitlines())

    start, end = _find_section_bounds(lines, tag)
    if start is not None and end is not None:
        updated = lines[:start] + section_lines + lines[end:]
    else:
        insert_at = _insert_index(lines)
        updated = lines[:insert_at] + section_lines + lines[insert_at:]

    return "\n".join(updated).rstrip() + "\n"


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Semantic release tag, e.g. v0.1.0")
    parser.add_argument("--date", required=True, help="Release date in ISO format, e.g. 2026-07-12")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to changelog file (default: CHANGELOG.md)",
    )
    return parser.parse_args()


def main() -> int:
    """Generate or update the release section in CHANGELOG.md."""
    args = _parse_args()

    if not TAG_PATTERN.fullmatch(args.tag):
        print("ERROR: --tag must match semantic format vMAJOR.MINOR.PATCH", file=sys.stderr)
        return 2

    try:
        date.fromisoformat(args.date)
    except ValueError:
        print("ERROR: --date must be in ISO format YYYY-MM-DD", file=sys.stderr)
        return 2

    changelog_path = Path(args.changelog)
    existing_text = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""

    previous_tag = _nearest_previous_tag(args.tag)
    commits = _collect_commit_subjects(previous_tag)
    section_lines = _build_section(args.tag, args.date, previous_tag, commits)
    new_text = _upsert_section(existing_text, args.tag, section_lines)

    changelog_path.write_text(new_text, encoding="utf-8")
    print(f"Updated {changelog_path} for {args.tag} ({args.date})")
    print(f"Commit count in release delta: {len(commits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
