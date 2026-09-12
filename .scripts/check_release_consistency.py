"""Assert that a release tag agrees with everything the repository declares about it.

The release process bumps several files by hand, and a checklist is not a control:
v0.5.0 published with ``terminal_setup.__version__`` still reading 0.1.0 while every
gate passed, because nothing compared the two. Nothing compared the *tag* to either
of them, so a tag cut on an unbumped tree would have published just as quietly.

Run before tagging, and again as the release workflow's first step, so that
forgetting the pre-flight is caught rather than trusted.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

TAG_PATTERN = re.compile(r"^v(?P<version>\d+\.\d+\.\d+)$")
VERSION_ATTR_PATTERN = re.compile(r'^__version__\s*=\s*"(?P<version>[^"]+)"', re.MULTILINE)
LOCK_PROJECT_PATTERN = re.compile(
    r'^name = "terminal"\nversion = "(?P<version>[^"]+)"', re.MULTILINE
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def pyproject_version(repo_root: Path) -> str:
    """Return ``[project] version``, the version the build publishes."""
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["project"]["version"]


def module_version(repo_root: Path) -> str:
    """Return ``__version__`` by reading the source, not by importing it.

    Importing would resolve through any stale bytecode or a shadowing
    ``terminal.egg-info`` on ``sys.path``, which is how a wrong value already
    survived one investigation.
    """
    source = repo_root / "terminal_setup" / "__init__.py"
    match = VERSION_ATTR_PATTERN.search(source.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"no __version__ assignment found in {source}")
    return match.group("version")


def lock_version(repo_root: Path) -> str | None:
    """Return the project version uv.lock records, or None when it records none.

    Checked because a bare ``uv sync`` re-resolves and rewrites a stale lockfile
    rather than failing on it, so the drift is masked wherever it is not asserted.
    """
    match = LOCK_PROJECT_PATTERN.search((repo_root / "uv.lock").read_text(encoding="utf-8"))
    return match.group("version") if match else None


def changelog_heading(repo_root: Path, tag: str) -> str | None:
    """Return the dated changelog heading for ``tag``, or None when absent."""
    pattern = re.compile(rf"^## {re.escape(tag)} - (\d{{4}}-\d{{2}}-\d{{2}})$", re.MULTILINE)
    text = (repo_root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = pattern.search(text)
    return match.group(0) if match else None


def check(tag: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Return one message per disagreement; an empty list means consistent."""
    tag_match = TAG_PATTERN.match(tag)
    if tag_match is None:
        return [f"tag {tag!r} is not a semantic release tag of the form vX.Y.Z"]

    expected = tag_match.group("version")
    problems: list[str] = []

    declared = (
        ("pyproject.toml [project] version", pyproject_version(repo_root)),
        ("terminal_setup/__init__.py __version__", module_version(repo_root)),
        ("uv.lock project version", lock_version(repo_root)),
    )
    for label, actual in declared:
        if actual is None:
            problems.append(f"{label} could not be read")
        elif actual != expected:
            problems.append(f"{label} is {actual}, but the tag says {expected}")

    if changelog_heading(repo_root, tag) is None:
        problems.append(
            f"CHANGELOG.md has no '## {tag} - YYYY-MM-DD' heading; run "
            f".scripts/generate_release_changelog.py --tag {tag} --date YYYY-MM-DD"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    """Report each disagreement, or confirm the release is consistent."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", required=True, help="the release tag, for example v0.6.0")
    args = parser.parse_args(argv)

    problems = check(args.tag)
    if problems:
        print(f"Release {args.tag} is inconsistent:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"Release {args.tag} is consistent:")
    print(f"  {'pyproject.toml':<16} {pyproject_version(REPO_ROOT)}")
    print(f"  {'__version__':<16} {module_version(REPO_ROOT)}")
    print(f"  {'uv.lock':<16} {lock_version(REPO_ROOT)}")
    print(f"  {'CHANGELOG.md':<16} {changelog_heading(REPO_ROOT, args.tag)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
