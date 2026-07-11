# Agent Baseline

Canonical, tool-agnostic rules for coding agents in this repo.

This is the single shared baseline. Keep tool-specific details in
`.claude/` and `.github/`; do not duplicate policy across files.

## Use

- Read this file before taking action.
- Re-read after context resets or long tool chains.
- User instructions in the current task override this file.
- More specific path-scoped instructions override this file for matching files.

## Project Defaults

- Scope: cross-platform terminal tooling and automation.
- Platforms: Windows, Linux, macOS.
- Python: managed with `uv`.
- Script harness and CI helpers: `.scripts/`.
- Shared skills: `.claude/skills/`.
- No global build/test command yet; run only commands configured by task/subproject.

## Core Rules

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

## Require Explicit Confirmation

- Force-push, history rewrite, or destructive git resets.
- Deleting files/branches/data beyond explicit task scope.
- Editing CI/CD, deployment, infra-as-code, ignore/secrets files, or `.env*`.
- Adding/removing/upgrading dependencies.
- New network calls outside task scope.
- Skipping or weakening tests/lint/type checks to force success.

## Quality Gate

- Review the diff before finishing.
- Run relevant checks/tests for changed behavior.
- Do not mark complete with "should work"; verify.

## If Stuck

- State missing information and ask instead of guessing.
- If rules conflict, prefer safety/security boundaries.
- If repeated attempts fail, stop and report the failure pattern.
