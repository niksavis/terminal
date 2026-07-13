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

## Maintainer steps

1. Ensure `main` is green and all release code changes are committed.
1. Bump `version` in `pyproject.toml` to match the target tag, refresh `uv.lock` (`uv lock`), and commit both, for example `git commit -m "chore(release): bump package version for next release"`.
1. Generate/update changelog for the target semantic tag and date with `uv run python .scripts/generate_release_changelog.py --tag vX.Y.Z --date YYYY-MM-DD`.
1. Review `CHANGELOG.md`: keep a concise user-facing `### Highlights` section above the auto-generated commit delta.
1. Commit changelog updates with `git add CHANGELOG.md && git commit -m "docs(release): update changelog for vX-Y-Z"`.
1. Push `main` with `git push origin main`.
1. Create an annotated semantic version tag with the release date in the message using `git tag -a vX.Y.Z -m "vX.Y.Z (YYYY-MM-DD)"`.
1. Push the tag with `git push origin vX.Y.Z`.
1. Review the generated GitHub release page and verify notes were copied from `CHANGELOG.md`.

> **Note:** The commit-msg hook only allows lowercase letters, digits, spaces, and hyphens in the commit description - no dots or commas. Write versions as `v0-2-1` (not `v0.2.1`) in commit subjects; tags themselves keep the normal `vX.Y.Z` form.
