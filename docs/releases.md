# Releases

Maintainer notes for publishing tagged releases.

## What users run

- Latest from main:
  - `uvx --from git+https://github.com/niksavis/terminal@main terminal-setup`
- Pinned release (from release page):
  - `uvx --from git+https://github.com/niksavis/terminal@vX.Y.Z terminal-setup`

## Release workflow

- File: `.github/workflows/release.yml`
- Triggered on tag push (`v*`) and tag create events.
- Creates/updates a GitHub release with:
  - brief notes auto-generated from commit subjects since previous tag
  - pinned `uvx` install command for that tag

## Maintainer steps

1. Ensure `main` is green and docs are up to date.
2. Create a version tag (example):
   - `git tag v0.1.0`
3. Push the tag:
   - `git push origin v0.1.0`
4. Review the generated GitHub release page and notes.
