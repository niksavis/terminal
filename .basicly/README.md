# basicly (vendored bridge)

A source-of-truth projector that generates AI agent configuration files from small, tool-agnostic Markdown fragments.

## Why

Keep agent instructions (Claude Code, GitHub Copilot, Codex, etc.) in one place. Author a rule once as a fragment, then project it to each target's native format and activation rules.

## Provenance

This repo consumes `basicly` ahead of its packaged release. Until `uvx`
installation ships, the engine is **vendored** at `.basicly/basicly/` as a
temporary bridge, copied verbatim from the `basicly` repository:

- Source: `basicly` repository, `src/basicly/` at commit
  `edb2b7e7be5007c8fe0d747ca2e9d7080e8a9cdc`.
- The engine's test suite lives in the `basicly` repository (not vendored here);
  because the copy is byte-identical to that commit, upstream coverage applies.
- Two catalog skills (`conventional-commits`, `tool-br`) are intentionally
  excluded from `core/skills/`: they mandate a beads issue-tracker commit
  workflow this repo does not use, and the catalog has no per-consumer
  selection mechanism yet.
- When re-syncing, copy `src/basicly/` over `.basicly/basicly/`, strip
  `__pycache__`, re-apply the skill exclusions above, and update the commit
  hash here.

Once `basicly` is installable via `uvx`, delete `.basicly/basicly/` and switch
the invocations below (and `.github/workflows/basicly.yml`) to the installed CLI.

## Layout

This directory contains the catalog data a consumer repo has after
`basicly init`/`update`, plus the vendored engine noted above.

```text
.basicly/
  basicly/        # vendored engine (temporary bridge; see Provenance)
  core/
    fragments/    # managed core fragments shipped by basicly (guidance, non-deterministic)
    skills/       # managed skill catalog shipped by basicly
    hooks/        # managed git hook scripts (gating, deterministic) - see hooks/README.md
    targets/      # per-target registry files (YAML)
    templates/    # Jinja2 templates for each target
  generated-manifest.json  # deterministic projection record

.basicly-local/
  fragments/      # user-owned overlay fragments (this repo's own rules)
```

Fragments and skills are the **suggestive** half of the harness (Markdown guidance a
model reads); hooks under `core/hooks/` are the **gating** half (scripts that
mechanically block a bad commit/push).

## Fragments

Each fragment is a Markdown file with YAML front matter:

```markdown
---
id: python-style
description: Python style conventions for this repo.
category: code-style
priority: medium
applies_to: [all]
scope:
  paths: ["**/*.py"]
---

- Use type hints for public functions.
- Prefer `pathlib` over `os.path`.
- Format with `ruff`.
```

Fields:

- `id` — stable, unique identifier.
- `description` — one-line summary.
- `category` — controlled vocabulary (e.g. `project`, `code-style`, `security`).
- `applies_to` — list of target names, or `[all]` for cross-tool baseline.
- `priority` — `critical` | `high` | `medium` | `low`.
- `scope.paths` — glob list; non-default scopes produce path-scoped outputs.
- `status` — `active` | `draft` | `deprecated`.
- `title` — optional display heading.
- `source` — `"core"` or `"user"` (inferred from load root if omitted).
- `override` — boolean, allows a user fragment to replace core fragments.
- `replaces` — list of fragment ids to remove when this fragment is active.
- `extends` — list of fragment ids this fragment augments (documentation only).

## Targets

Targets are defined in `.basicly/core/targets/<name>.yaml`. Each target declares its outputs, templates, and fragment selection rules.

## CLI

Run from the repository root:

```bash
# List active fragments
PYTHONPATH=.basicly uv run python -m basicly.cli list

# Refresh managed core layout only
PYTHONPATH=.basicly uv run python -m basicly.cli update

# Build all enabled targets
PYTHONPATH=.basicly uv run python -m basicly.cli build

# Build only one target
PYTHONPATH=.basicly uv run python -m basicly.cli build --target claude

# Check generated files are up to date (CI gate)
PYTHONPATH=.basicly uv run python -m basicly.cli check

# List source skill collection entries
PYTHONPATH=.basicly uv run python -m basicly.cli skills-list

# Project skills into .claude/skills (default)
PYTHONPATH=.basicly uv run python -m basicly.cli skills-build

# Project skills into all default roots
PYTHONPATH=.basicly uv run python -m basicly.cli skills-build --all-default-roots

# Check projected skills are synchronized
PYTHONPATH=.basicly uv run python -m basicly.cli skills-check
```

## CI

The `.github/workflows/basicly.yml` workflow runs `check` on every push and pull request to `main`.

## Adding a fragment

1. Repo-specific fragments go under `.basicly-local/fragments/user/<category>/`
   (the overlay; never touched by `basicly update`). Core fragments under
   `.basicly/core/fragments/` are managed catalog content — don't hand-edit them.
2. Set `applies_to` to `[all]` for cross-tool rules, or to specific target names.
3. To supersede a core fragment instead of adding alongside it, set
   `override: true` and `replaces: [<core-id>]` in the overlay fragment.
4. Run `build` and commit the updated generated files and manifest.

## Path configuration

Paths are configured in `basicly.toml`:

1. `paths.core_fragments`
2. `paths.overlay_fragments`
3. `paths.targets`
4. `paths.templates`
5. `paths.manifest`

This allows users to choose a custom overlay folder name instead of `.basicly-local`.

## Skill collection

`basicly` also supports a repository-controlled skill catalog:

- Source of truth: `.basicly/core/skills/<skill-name>/SKILL.md`
- Projection roots (optional): `.claude/skills`, `.github/skills`, `.agents/skills`
- Default behavior: `skills-build` syncs source skills into `.claude/skills`

Projection never deletes extra files, so repo-authored skills (e.g.
`.claude/skills/release-process/`) coexist with projected catalog skills.

## Git hooks

`basicly` ships git hook scripts as a catalog artifact under
[`core/hooks/`](core/hooks/README.md) — the deterministic, gating counterpart to
fragments/skills. **They are not wired in this repo**: the active git hooks live
at `.scripts/git-hooks/` and are wired via
[`.pre-commit-config.yaml`](../.pre-commit-config.yaml). The catalog copies stay
as shipped so a future `hooks-build`/`hooks-check` projection can adopt them
deliberately; note the catalog `commit-msg.py` enforces a stricter format
(beads issue ids) than this repo's live hook, and the catalog `pre-commit.py`
lacks this repo's cheat-sheet render check.
