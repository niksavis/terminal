---
id: core-rules
description: Core rules that apply to all work in this repo.
category: project
priority: high
applies_to: [all]
tags: [rules, quality]
status: active
---

- Prioritize correctness over speed.
- Keep diffs minimal; avoid unrelated refactors/reformatting.
- Prefer explicit, readable solutions over clever ones.
- Do not speculate; solve the stated requirement only.
- Back claims with evidence from this session (files read, commands run, tests).
- Keep code clean: no dead code, debug prints, or silent error swallowing.
- Match existing style and naming conventions in touched files.
- Use deterministic tests; add regression tests for bug fixes.
- Keep secrets out of code/logs; validate external input.
- Prefer cross-platform implementations over shell-specific behavior.
- Check lockfiles/config before choosing package managers or tooling.
