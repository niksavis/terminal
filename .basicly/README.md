# basicly

A source-of-truth projector that generates AI agent configuration files from small, tool-agnostic Markdown fragments.

## Why

Keep agent instructions (Claude Code, GitHub Copilot, Codex, etc.) in one place. Author a rule once as a fragment, then project it to each target's native format and activation rules.

## Layout

```text
.basicly/
  fragments/      # tool-agnostic policy fragments (Markdown + YAML front matter)
  targets/        # per-target registry files (YAML)
  templates/      # Jinja2 templates for each target
  basicly/        # engine: loader, planner, renderers, CLI
  tests/          # engine tests
  generated-manifest.json  # deterministic projection record
```

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
- `source` — `"core"` or `"user"` (reserved for phase 2; defaults to `"core"`).
- `override` — boolean, allows a user fragment to replace core fragments (reserved).
- `replaces` — list of fragment ids to remove when this fragment is active (reserved).
- `extends` — list of fragment ids this fragment augments (reserved).

## Targets

Targets are defined in `.basicly/targets/<name>.yaml`. Each target declares its outputs, templates, and fragment selection rules.

## CLI

Run from the repository root:

```bash
# List active fragments
PYTHONPATH=.basicly uv run python -m basicly.cli list

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

1. Create a new `.fragment.md` file under `.basicly/fragments/<category>/`.
2. Set `applies_to` to `[all]` for cross-tool rules, or to specific target names.
3. Run `build` and commit the updated generated files and manifest.

## Adding a target

1. Add a renderer module at `.basicly/basicly/renderers/<name>.py`.
2. Add templates under `.basicly/templates/<name>/`.
3. Add a registry file at `.basicly/targets/<name>.yaml`.
4. Run `build` and commit.

## Skill collection

`basicly` also supports a repository-controlled skill catalog:

- Source of truth: `.basicly/skills/<skill-name>/SKILL.md`
- Projection roots (optional): `.claude/skills`, `.github/skills`, `.agents/skills`
- Default behavior: `skills-build` syncs source skills into `.claude/skills`

This keeps skills shippable when extracting the `basicly` engine into a standalone repository while still allowing downstream repos to consume projected skill files.

## User customizations (phase 2 preview)

The `.basicly/fragments/user/` directory is reserved for user-added fragments that
survive updates to the core fragments shipped with basicly. The schema already accepts
`source`, `override`, `replaces`, and `extends` fields with safe defaults. The full
verification and override workflow is planned in
[`.plan/source-of-truth-projector-extensions.md`](../.plan/source-of-truth-projector-extensions.md).

## Extracting basicly

The engine in `.basicly/basicly/` and templates in `.basicly/templates/` have no terminal-specific content. To reuse basicly in another repo:

1. Copy `.basicly/basicly/` and `.basicly/templates/`.
2. Replace `.basicly/fragments/` and `.basicly/targets/` with the new repo's content.
3. Keep the CLI interface and manifest format unchanged.
