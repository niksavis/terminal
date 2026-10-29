## Where guidance lives

| Type | Loaded | Projected to | Build, then check |
| --- | --- | --- | --- |
| Fragment | Always, merged into `CLAUDE.md`, `AGENTS.md` and `copilot-instructions.md`, or into per-path rule files when scoped | the instruction files | `basicly build`, `basicly check` |
| Skill | On demand, when its `description` matches the task | `SKILL.md` at each skill root | `basicly skills-build`, `basicly skills-check` |
| Output style | Always. It replaces the default answer format of Claude Code | `.claude/output-styles/<slug>.md` | `basicly styles-build`, `basicly styles-check` |

Keep a fragment short. Point to a command, and do not restate a rule that a gate enforces.

## Author a skill

1. Run `basicly catalog new skill <slug>`. It writes `.basicly/core/skills/<slug>/skill.yaml`.
2. Set `name` equal to the slug.
3. Write the `description`. It is the discovery trigger, so say when to use the skill.
4. Write the `instructions` body as a `|` literal block of markdown, indented two spaces.
5. Run `basicly skills-build`, then `basicly skills-check`. With no arguments they cover every default root, as the `projection-skills` gate does.

## Author a fragment

1. Run `basicly catalog new fragment <id> --category <category>`. It writes `.basicly/core/fragments/<category>/<id>.fragment.yaml`. In a consumer repository, move the file under `.basicly-local/fragments/`.
2. Set `id`, `description`, `category`, `applies_to` (for example `[all]`) and the `body` block.
3. Optional fields: `priority`, `phase`, `tags`, `status`, `title`, `scope.paths` for a path-scoped rule, and the overlay fields `replaces` and `override`. `phase` (`start`, `plan`, `build`, `verify`, `ship` or `finish`) places the fragment in the workflow order of Always do. A fragment without a phase renders first in Always do, so a repository's own facts come before the shared workflow.
4. Run `basicly build`, then `basicly check`.

## Author an output style

1. Write `.basicly/core/output-styles/<slug>/style.yaml` with `name`, `description`, `body` and `keep_coding_instructions`. The directory name is the slug.
2. Run `basicly styles-build`, then `basicly styles-check`, as the `projection-styles` gate does.

Keep `keep_coding_instructions: true`, unless you intend to drop the built-in engineering instructions of the host. They include how to verify work.

## YAML shape

Start each source with the schema header and `schema_version`. Write the prose body as a literal block, so the markdown stays unchanged:

```yaml
# yaml-language-server: $schema=../../schemas/skill.schema.json
schema_version: 1
name: my-skill
description: What it does and when to use it.
instructions: |
  # My Skill
  ...
```

`technologies: [python]` limits a skill, fragment, agent or hook to one technology. The values come from a controlled vocabulary, and `basicly catalog lint` refuses any other value. A consumer selects with `basicly install --technologies ...`.
