# Releases

Maintainer notes for publishing tagged releases.

## What users run

- Latest from main:
  - `uvx --from git+https://github.com/niksavis/terminal@main terminal-setup`
- Pinned release (from release page):
  - `uvx --from git+https://github.com/niksavis/terminal@vX.Y.Z terminal-setup`

## Release workflow

- File: `.github/workflows/release.yml`
- Triggered on semantic tag push (`v*`).
- Uses the matching section in `CHANGELOG.md` as release notes source.
- Requires section heading format: `## vX.Y.Z - YYYY-MM-DD`.
- Appends a pinned `uvx` install command for that tag.
- Runs the full `quality-gates` suite against the tagged tree and will not publish unless it passes; neither gate workflow triggers on tags, so before this a tag inherited its green from `main` having been pushed first.
- Runs `.scripts/check_release_consistency.py` and fails the release when the tag disagrees with `pyproject.toml`, `terminal_setup/__init__.py`, `uv.lock` or the changelog heading. The pre-flight step below is the same check run earlier; this one is what makes skipping it harmless, since a tag cut on an unbumped tree cannot publish.

## Maintainer steps

1. Ensure `main` is green and all release code changes are committed. File or claim the tracker record the release belongs to; every commit subject below ends with its id, for example `(term-abc12)`.
1. Bump `version` in `pyproject.toml` **and** `__version__` in `terminal_setup/__init__.py` to match the target tag, refresh `uv.lock` (`uv lock`), and commit them together, for example `git commit -m "chore(release): bump package version for next release (term-abc12)"`. The two must agree: `tests/test_version.py` fails when they drift, which is how `__version__` was caught sitting at 0.1.0 through every release up to v0.5.0.
1. Generate/update changelog for the target semantic tag and date with `uv run python .scripts/generate_release_changelog.py --tag vX.Y.Z --date YYYY-MM-DD`.
1. Review `CHANGELOG.md`: keep a concise user-facing `### Highlights` section above the auto-generated commit delta.
1. Stage the changelog with `git add CHANGELOG.md`, then commit it on its own with `git commit -m "docs(release): update changelog for vX-Y-Z (term-abc12)"`.
1. Push `main` with `git push origin main`.
1. Check the release is internally consistent with `uv run python .scripts/check_release_consistency.py --tag vX.Y.Z`. It compares the tag against `pyproject.toml`, `terminal_setup/__init__.py`, `uv.lock` and the `CHANGELOG.md` heading, and names every disagreement at once. Run it here so a mismatch is fixed before a tag exists to retract.
1. Create an annotated semantic version tag with the release date in the message using `git tag -a vX.Y.Z -m "vX.Y.Z (YYYY-MM-DD)"`.
1. Push the tag with `git push origin vX.Y.Z`.
1. Review the generated GitHub release page and verify notes were copied from `CHANGELOG.md`.

> **Note:** The commit-msg hook only allows lowercase letters, digits, spaces, and hyphens in the commit description - no dots or commas. Write versions as `v0-2-1` (not `v0.2.1`) in commit subjects; tags themselves keep the normal `vX.Y.Z` form. The tracker-commit-msg hook refuses a subject that does not end with a record id the ledger holds.
