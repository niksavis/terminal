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
- Solve the stated requirement only — no speculative abstractions or unrequested config.
- Search for existing helpers, utilities, or patterns in this codebase before writing new code; reuse before reinventing.
- Fix the root cause, not the symptom: grep other callers before assuming a single-call-site patch is complete.
- Back claims with evidence from this session (files read, commands run, tests) — do not assert without checking.
- Keep code clean: no dead code, debug prints, or silent error swallowing.
- Match existing style and naming conventions in touched files.
- Use deterministic tests; add regression tests for bug fixes.
