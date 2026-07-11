# Agent Tool Skill Catalog Plan

## Objective

Create a hardened, repository-controlled skill catalog for the terminal tool baseline, with projection support for default and user-defined skill directories.

## Baseline Tools

- git
- ripgrep
- fd
- jq
- yq
- fzf
- bat
- tree
- xh
- shellcheck
- ast-grep
- sd
- delta
- typos
- uv

## Current State

- Installer baseline updated to agent-first tool set.
- Tests hardened for tool-install package lists and version output resilience.
- Initial `skill-creator` skill added at `.claude/skills/skill-creator/SKILL.md`.

## Phase 1: Skill Framework Foundations

1. Define canonical skill schema for this repo.

- Required frontmatter: `name`, `description`.
- Required sections: when-to-use, commands, pitfalls, outputs.

1. Define projection targets.

- Default roots: `.claude/skills`, `.github/skills`, `.agents/skills`.
- Add support for user-defined output root (config/env/CLI).

1. Decide projection ownership.

- Preferred: implement in repo automation (basicly or script harness), not manual duplication.

## Phase 2: Create Tool Skills

Create one skill folder per baseline tool using `skill-creator` workflow:

1. Draft skill.
2. Add trigger and anti-trigger examples.
3. Add command cookbook and safety notes.
4. Validate trigger quality against realistic prompts.

Planned skill IDs:

- tool-git
- tool-ripgrep
- tool-fd
- tool-jq
- tool-yq
- tool-fzf
- tool-bat
- tool-tree
- tool-xh
- tool-shellcheck
- tool-ast-grep
- tool-sd
- tool-delta
- tool-typos
- tool-uv

## Phase 3: Projection and Consumption

1. Implement projection command to publish skill catalog into selected roots.
2. Support custom destination path for downstream repos that consume extracted basicly output.
3. Add idempotent sync behavior (create/update, no destructive deletes unless requested).

## Phase 4: Verification and CI

1. Add tests for:

- Skill folder shape (`<name>/SKILL.md`).
- Frontmatter requirements.
- Projection output correctness for each target root.

1. Add a repo check task to validate the skill catalog and projection output.

## Acceptance Criteria

- All baseline tools have skills with consistent structure.
- Skills are discoverable in at least one default root.
- Projection supports all three default roots and user-defined destination.
- Tests and checks pass in CI.
- Skill catalog remains fully repository-controlled.

## Next Session First Actions

1. Read `.claude/skills/skill-creator/SKILL.md`.
2. Implement projection design decision (config source + command).
3. Generate first 3 tool skills (`ripgrep`, `fd`, `jq`) as templates for the rest.
