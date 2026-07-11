# Copilot Defaults

See `AGENTS.md` for shared rules. Keep this file Copilot-specific.

Copilot does not support `@`-style imports. If AGENTS context import fails,
temporarily mirror critical rules here and keep both files in sync.

## Copilot-specific notes

- Keep cross-agent policy in `AGENTS.md`; avoid duplication.
- Put path-scoped instructions in `.github/instructions/*.instructions.md`.
- Put prompts in `.github/prompts/*.prompt.md`.
- Put custom agents in `.github/agents/*.agent.md`.
- Put hooks in `.github/hooks/*.json`.
- Keep shared skills in `.claude/skills/` for Claude + Copilot reuse.
- Reference `.scripts/` entry points instead of long inline command blocks.
