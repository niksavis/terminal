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
1. Generate/update changelog for the target semantic tag and date with `uv run python .scripts/generate_release_changelog.py --tag v0.1.0 --date 2026-07-12`.
1. Review `CHANGELOG.md` and edit text for end-user clarity when needed.
1. Commit changelog updates with `git add CHANGELOG.md && git commit -m "docs(release): update changelog for v0.1.0"`.
1. Push `main` with `git push origin main`.
1. Create an annotated semantic version tag with the release date in the message using `git tag -a v0.1.0 -m "v0.1.0 (2026-07-12)"`.
1. Push the tag with `git push origin v0.1.0`.
1. Review the generated GitHub release page and verify notes were copied from `CHANGELOG.md`.
