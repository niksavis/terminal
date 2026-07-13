---
id: copilot-defaults
description: Copilot-specific defaults and file layout conventions.
category: project
priority: medium
applies_to: [copilot]
tags: [copilot, layout]
status: active
title: Copilot-specific notes
---

- Put path-scoped instructions in `.github/instructions/*.instructions.md`.
- Put prompts in `.github/prompts/*.prompt.md`.
- Put custom agents in `.github/agents/*.agent.md`.
- Put hooks in `.github/hooks/*.json`.
- Keep shared skills in `.claude/skills/` for Claude + Copilot reuse.
