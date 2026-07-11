---
id: claude-defaults
description: Claude-specific defaults and file layout conventions.
category: project
priority: medium
applies_to: [claude]
tags: [claude, layout]
status: active
title: Claude-specific notes
---

- Keep cross-agent policy in `AGENTS.md`; avoid duplication.
- Put reusable skills in `.claude/skills/`.
- Put Claude-only prompts/commands/runbooks in `.claude/*.md`.
- Prefer cross-platform commands.
- Prefer `.scripts/` entry points over long inline command blocks.
