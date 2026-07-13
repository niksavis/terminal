---
name: skill-creator
description: Create and improve reusable agent skills in this repository. Use this whenever the user asks to add a new skill, update an existing skill, build a skill catalog, or improve how/when a skill triggers.
---

# Skill Creator

Create practical, reusable skills for this repository with a consistent structure and strong trigger descriptions.

## Goals

- Produce a clear, reliable `SKILL.md` for each skill.
- Make trigger descriptions explicit so skills are used when needed.
- Keep instructions concise, actionable, and safe.
- Keep all skills repository-controlled.
- Keep generated guidance portable and privacy-safe (no user-specific paths, usernames, or secrets).

## Scope and Non-Goals

This skill is for creating and improving skill documentation and trigger quality.

It is not for:

- Runtime debugging of unrelated project code.
- Broad refactors outside the requested skill scope.
- Changing CI, dependencies, or infra as part of skill wording edits.

## Skill Locations

Preferred shared location in this repository:

- `.claude/skills/<skill-name>/SKILL.md`

Common discovery roots to support when requested:

- `.claude/skills/`
- `.github/skills/`
- `.agents/skills/`

If the user asks for projection or install into a custom location, create/update repository automation instead of manually duplicating files.

## Required SKILL.md Format

Each skill must include:

- Part 1: YAML frontmatter with:
  - `name`
  - `description` (must include both what the skill does and when to use it)
- Part 2: A markdown body with:
  - Purpose and scope
  - Inputs/outputs
  - Step-by-step workflow
  - Guardrails and non-goals
  - Examples or command snippets when useful

## Output Contract

When this skill is used, produce:

1. A revised or new `SKILL.md` with complete frontmatter and trigger-focused description.
2. A short summary of what changed and why.
3. A validation note confirming lint/format checks relevant to the edited file.

## Authoring Workflow

1. Capture intent: what should this skill enable, when should it trigger, and what output should it produce.
2. Define boundaries: what this skill does and what this skill does not do.
3. Draft the skill: write a strong trigger-focused description, use imperative concrete instructions, and keep it short enough to load quickly.
4. Add practical examples: include realistic prompt examples and command examples when relevant.
5. Validate trigger quality: create 2-3 should-trigger prompts, create 2-3 should-not-trigger prompts, and refine `description` until behavior is precise.
6. Integrate with repo automation: if this repo needs projection to multiple skill roots, implement that through repo scripts/config (not manual copy-paste workflows).

## Writing Standards

- Prefer clarity over length.
- Explain why key steps matter.
- Avoid over-constraining language unless safety requires it.
- Avoid tool- or platform-lock-in unless explicitly required.
- Never include malicious, deceptive, or unsafe guidance.
- Avoid user-specific machine details (home directories, usernames, hostnames, tokens, private URLs).
- Prefer repo-relative paths and generic placeholders in examples.

## Tool-Specific Skill Pattern

For CLI tool skills (for example `ripgrep`, `fd`, `jq`, `ast-grep`), use this pattern:

1. When to use
2. Fast start commands
3. Safe defaults
4. Common pitfalls
5. Output interpretation
6. Repo-specific conventions

## Done Criteria

A new/updated skill is complete when:

- It is in a discoverable folder.
- Frontmatter `name` and trigger-ready `description` are present.
- Instructions are actionable and tested against realistic prompts.
- Scope and guardrails are explicit.
- The user confirms the behavior matches intent.

## Validation Checklist

Before finishing a skill update:

1. Confirm should-trigger prompts clearly map to the skill description.
2. Confirm should-not-trigger prompts are excluded by scope language.
3. Verify markdown lint passes for edited skill docs.
4. Verify examples do not leak user-specific or machine-local information.
