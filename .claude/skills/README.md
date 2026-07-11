# Skills Folder

Place reusable workflow skills under this directory.

Most tool skills are projected from `.basicly/skills/` via:

```bash
PYTHONPATH=.basicly uv run python -m basicly.cli skills-build
```

The `skill-creator` skill may still be maintained directly in this folder.

## Structure

Each skill should have its own folder and include a `SKILL.md` file, for example:

- `.claude/skills/<skill-name>/SKILL.md`

This location is intended to be shared by both Claude and GitHub Copilot.
