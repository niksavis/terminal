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

1. YAML frontmatter with:
- `name`
- `description` (must include both what the skill does and when to use it)

2. A markdown body with:
- Purpose and scope
- Inputs/outputs
- Step-by-step workflow
- Guardrails and non-goals
- Examples or command snippets when useful

## Authoring Workflow

1. Capture intent.
- What should this skill enable?
- When should it trigger?
- What output should it produce?

2. Define boundaries.
- What this skill does
- What this skill does not do

3. Draft the skill.
- Write a strong trigger-focused description.
- Use imperative, concrete instructions.
- Keep it short enough to load quickly.

4. Add practical examples.
- Include realistic prompt examples.
- Include command examples when relevant.

5. Validate trigger quality.
- Create 2-3 should-trigger prompts.
- Create 2-3 should-not-trigger prompts.
- Refine `description` until behavior is precise.

6. Integrate with repo automation.
- If this repo needs projection to multiple skill roots, implement that through repo scripts/config (not manual copy-paste workflows).

## Writing Standards

- Prefer clarity over length.
- Explain why key steps matter.
- Avoid over-constraining language unless safety requires it.
- Avoid tool- or platform-lock-in unless explicitly required.
- Never include malicious, deceptive, or unsafe guidance.

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
