---
name: release-process
description: Prepare and publish semantic version releases using this repository's changelog-driven workflow. Use this when asked to cut a release, update CHANGELOG.md for a tag, review release notes quality, create/push tags, or verify GitHub release status.
---

# Release Process

Run the repository release flow end-to-end with semantic tags and dated changelog sections.

## Scope

This skill handles release preparation and publication for this repository.

It is not for:

- Editing unrelated product features.
- Rewriting git history.
- Skipping quality gates.

## Inputs

- Target semantic tag (for example `v0.1.1`).
- Release date in ISO format (`YYYY-MM-DD`).
- Optional manual edits to changelog highlights before tagging.

## Outputs

- Updated `CHANGELOG.md` section for the target tag.
- Tag pushed to origin.
- GitHub release created by workflow with notes sourced from changelog.
- Verification summary with run URL and release URL.

## Workflow

1. Verify branch state and quality gates.

- Confirm working tree is clean.
- Confirm required checks pass locally (`pre-commit`, tests) when relevant.

1. Ensure release changes are committed first.

- Commit any release workflow/tooling updates before generating changelog for the new tag.

1. Generate changelog section.

- Run:
- `uv run python .scripts/generate_release_changelog.py --tag vX.Y.Z --date YYYY-MM-DD`
- This computes commit delta from previous semantic tag to `HEAD`.

1. Review changelog text for end-user clarity.

- Keep a concise `### Highlights` section.
- Keep `### Commit delta (auto-generated)` for traceability.
- Ensure heading format is exact: `## vX.Y.Z - YYYY-MM-DD`.

1. Commit changelog update.

- `git add CHANGELOG.md`
- `git commit -m "docs(release): update changelog for <release>"`

1. Push main branch.

- `git push origin main`

1. Create annotated semantic tag with date.

- `git tag -a vX.Y.Z -m "vX.Y.Z (YYYY-MM-DD)"`
- `git push origin vX.Y.Z`

1. Verify release publication.

- Check release workflow run status.
- Confirm GitHub release body matches the tag section from `CHANGELOG.md` plus the pinned `uvx` install line.

## Guardrails

- Never force-push or rewrite history for release flow unless explicitly requested.
- Never tag from a dirty working tree.
- Never skip CI/quality gate failures.
- Do not include user-specific local paths or secrets in changelog/release notes.

## Trigger Examples

Should trigger:

- "Cut v0.1.2 release and publish notes."
- "Generate release notes from changelog and tag."
- "Prepare next semantic release with date and push tag."

Should not trigger:

- "Fix this installer bug in prerequisites.py."
- "Refactor tmux config keybindings."
- "Explain how CHANGELOG works conceptually."
