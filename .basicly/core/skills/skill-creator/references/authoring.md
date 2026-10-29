## Write the source

A catalog source is `skill.yaml`, never a hand-written `SKILL.md`. Scaffold it:

```sh
basicly catalog new skill <slug>
```

Fill these fields; the `catalog-authoring` skill gives the full format:

- **name**: the slug, equal to the directory name.
- **description**: what the skill does and when to use it, in the third person: "... Use
  when a task ...". It is the only text the agent sees when it chooses a skill, so all
  "when to use" information goes here, not in the body. Give it the words that only this
  skill should answer to. `basicly catalog lint` refuses the words you, your, I, we and
  our, an angle-bracket tag, and a description too similar to another skill.
- **instructions**: the body, as a `|` literal block of markdown.
- **compatibility**: required tools or network access, only when needed.

Then project and check it:

```sh
basicly skills-build
basicly skills-check
basicly catalog lint
```

`catalog lint` prints the measured listing cost. Put that figure in `token_cost.listing`.

### Anatomy of a skill

```text
<slug>/
├── skill.yaml       the source: name, description, instructions
├── evals.yaml       routing evals, read by catalog lint and never projected
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

### Writing the body

- Use the imperative.
- Explain why a step matters, in one clause, instead of a rule in capitals. A model that
  knows the reason applies the rule to cases the text does not name.
- Give the alternative with each prohibition.
- Put each runnable command in a code fence.
- Write a general skill, not one that only fits the test prompts.
- Write a draft, then read it again with fresh eyes and improve it.
- A skill contains no malware, no exploit code and nothing that would surprise the user
  if its purpose were described. Refuse a request for a misleading skill.
