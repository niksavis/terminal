# Releases

Maintainer notes for publishing tagged releases.

## What users run

- Latest release (README):
  - `irm https://github.com/niksavis/terminal/releases/latest/download/install.ps1 | iex`
  - `curl -LsSf https://github.com/niksavis/terminal/releases/latest/download/install.sh | sh`
- One fixed release (release page):
  - `irm https://github.com/niksavis/terminal/releases/download/vX.Y.Z/install.ps1 | iex`
  - `uvx --from https://github.com/niksavis/terminal/archive/vX.Y.Z.zip terminal-setup` (no git needed)

`releases/latest` skips drafts and pre-releases. A test (`tests/test_terminal_setup/test_bootstrap.py`) refuses a user doc that points at `main`.

## Test unreleased main

For maintainers only. These commands install code that no release has checked:

- `irm https://raw.githubusercontent.com/niksavis/terminal/main/install.ps1 | iex`
- `curl -LsSf https://raw.githubusercontent.com/niksavis/terminal/main/install.sh | sh`
- `uvx --refresh-package terminal --from https://github.com/niksavis/terminal/archive/main.zip terminal-setup`

The scripts in the repository default to `main`, so a clone and the e2e test run the code under test. Only the copies attached to a release default to the tag.

## Release workflow

- File: `.github/workflows/release.yml`
- Triggered on semantic tag push (`v*`).
- Uses the matching section in `CHANGELOG.md` as release notes source.
- Requires section heading format: `## vX.Y.Z - YYYY-MM-DD`.
- Appends the pinned install commands for that tag: PowerShell, `sh` and `uvx`.
- Writes `install.ps1` and `install.sh` with the default ref set to the tag (`.scripts/pin_bootstrap.py`), and attaches both to the release. The pin script refuses a tag that is not `vX.Y.Z`, and a script that does not hold exactly one default ref, so the release does not publish without them.
- Runs the full `quality-gates` suite against the tagged tree and will not publish unless it passes; neither gate workflow triggers on tags, so before this a tag inherited its green from `main` having been pushed first.
- Runs `.scripts/check_release_consistency.py` and fails the release when the tag disagrees with `pyproject.toml`, `terminal_setup/__init__.py`, `uv.lock` or the changelog heading. The pre-flight step below is the same check run earlier; this one is what makes skipping it harmless, since a tag cut on an unbumped tree cannot publish.

## End-to-end install test

- File: `.github/workflows/e2e-install.yml`
- Runs the real install, as a user runs it, on GitHub-hosted runners:

  | Job | Runner | What it checks |
  | --- | --- | --- |
  | `linux` | `ubuntu-latest` | `install.sh --unattended --agents all --report` exits with code 0 |
  | `macos` | `macos-latest` | the same, after `wget` is present |
  | `windows-wsl` | `windows-latest`, with Ubuntu 24.04 from `Vampire/setup-wsl` | `install.ps1 --unattended --agents all --report` exits with code 0 |
  | `windows-without-wsl` | `windows-latest`, no distro | setup stops at the prerequisite check and installs nothing |

- Triggers: each tag push (`v*`), and on demand from the Actions tab with **Run workflow**. On demand, you can set the ref to install and the `--agents` value.
- It does not block a release. `release.yml` does not wait for it, and it runs beside the release. Read its result on the Actions tab after the release.
- It installs the commit under test: the bootstrap scripts come from the checkout, and `TERMINAL_SETUP_REF` points the archive download at the same commit.
- Most tools install their latest release, so a run can fail when a tool changes upstream, with no change in this repository.

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
