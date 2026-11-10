## Write the source

This file adds what makes a skill work.

### Anatomy of a skill

```text
<slug>/
├── skill.yaml       the source: name, description, instructions
├── evals.yaml       trigger cases and at least 3 task cases; never projected
├── references/      documents the agent loads when the body points to them
├── scripts/         code for deterministic or repeated steps
└── assets/          templates and files used in output
```

Every file beside `skill.yaml`, except `evals.yaml`, is copied into each projection. Keep
test workspaces and eval sets out of this directory.

### Progressive disclosure

1. **Name and description**: in context on every turn.
2. **Body**: in context when the skill triggers. Keep it under 500 lines.
3. **Bundled files**: loaded or run when needed. A script can run without being read.

- Point to each reference file from the body and say when to read it.
- Keep references one level deep: a reference file does not point to a further one.
- Start a reference file over 100 lines with a `## Contents` list.
- When a skill covers several frameworks, put one reference file per framework and let
  the body say which to read.
