## Contents

- Write
- What a record must carry
- Write a readable card
- Refine a record
- What the tracker refuses
- Reference

## Write

With the engine installed, writes use the seam below. Standalone consumers use the
packaged tracker CLI with the ledger directory; no engine is required.

```sh
basicly tracker write -- create "Title" -t task -p 2 -d "## Context

<problem and intended outcome>" --acceptance "<the observable checks>" --json
basicly tracker write -- update <id> --status in_progress       # claims it: you become the holder
basicly tracker write -- update <id> --acceptance-criteria "When <event>, the <system> shall <response>."
basicly tracker write -- update <id> --add-label <label>      # adds to the current set
basicly tracker write -- update <id> --remove-label <label>
basicly tracker write -- comments add <id> "<what you learned>"
basicly tracker write -- dep add <child-id> <parent-id> -t parent-child
basicly tracker write -- close <id> --reason "<what shipped, the command and its result>"
```

The argv after `--` uses this grammar and no other. The seam refuses an invented form.
`--add-label` and `--remove-label` change the current set. Every other `update` flag
replaces the value. A label selects lanes for a supervised pass
(`basicly loop supervise --label`).

### Commit the tracker state

- Direct owner work: close only after the whole task is satisfied, before its resolving commit. Stage
  the ledger with the code in that commit. Do not make a separate close commit.
- Work in the loop: do not touch the ledger. The engine commits tracker state at
  provisioning, landing and ship. See the `harness-loop` skill.
- Put the id in parentheses after the Conventional Commits description:
  `feat(cli): add fragment loader (<prefix>-<id>)`. The `conventional-commits` skill writes
  the message.

## What a record must carry

`basicly policy dor <id>` refuses a record that has no meaningful Context, no acceptance criteria, or
a section that `[policy.type_sections]` requires for its type.

- A `template.json` in the ledger directory changes the rule for the engine and the kit.
  `"mode": "extend"` adds its `sections` and per-type `types`. `"mode": "override"`
  replaces the whole rule. The tracker refuses a malformed template by name.
- `tracker write` has no `--field`. Meet a template section with that heading and its
  content in the description.
- The tracker refuses a write of a field that no code reads. `fields` prints the table.

## Write a readable card

Use `## Context` for a short problem statement and intended outcome. Avoid repeating
the same facts as Trigger, Proposed work and Reason. Keep current activity, a concrete
blocker and the next step concise; distinguish planned work from observed results.

Acceptance criteria state observable completion conditions. Requirements add distinct
constraints and invariants; avoid repeating the context or criteria as filler.
Leave Requirements empty when no distinct constraints apply; an explicit project
template can require them. Independent validation assesses Context, every Acceptance
criterion and any Requirements together. Link concise evidence to the checks.

Keep 3C/INVEST assessments and review protocol details in the review evidence, not in
the card prose. Preserve historical events when updating the current description.

## Refine a record

Only when a record needs refinement or its evidence contract changed, read the review forms in `.basicly/core/kit/tracker/GUIDANCE.md`.
A task, bug or chore with `--field size=small` and exactly one acceptance criterion needs
no review: claim it, then `confirm` one check before close.
Explicit tasks, bugs and chores accept a compact checks-only review. Other types require
the full review; existing full reviews stay valid. Keep intent, criteria, ownership and
actual outcomes. Record real questions and decisions when needed. `dor` enforces recorded
evidence; the agent judges semantic quality.
Use `basicly tracker write -- review <id> --evidence '<JSON>'` before claim and
`basicly tracker write -- confirm <id> --evidence '<JSON>'` after the agreed checks.
The shared guidance defines both JSON shapes. Completed close needs current evidence;
use `--resolution cancelled` with an abandonment reason for work that will not ship.

A person writes or edits a story, often in the served page, and the page adds the label
`refine`. The record is not ready to build until a refinement pass:

```sh
python3 .basicly/core/kit/tracker/cli.py refine .basicly/ledger     # labelled refine, or failing dor
```

1. For each record, read it with `show`.
2. Rewrite it with `update`: Context, observable Acceptance criteria, any distinct Requirements, the
   type, the priority and the `dep` edges.
3. Run `dor`. When it passes, remove the label with `--remove-label refine`.

Keep the intent of the person. When the intent is not clear, add a comment with the
question and leave the label on.

## What the tracker refuses

Each refusal writes nothing and names the cause:

- an argv that the seam cannot translate, for example `update --estimate 5`
  (*has no owned-ledger equivalent*);
- `dep add` with no `-t`, because the edge type is part of the fact;
- a label flag on an `update` that names two ids (*a label write accumulates against one
  record's own set ... issue one write per record*);
- a status outside `open`, `in_progress`, `blocked`, `deferred`, `closed` (the nearest one
  is suggested), a priority outside 0-4, and a `close` without `--reason`;
- a field that no code reads (*is not in the field table, so nothing reads it*), an
  import-history field, and a derived date.

A return to a status that the record held before is recorded.

## Reference

- **Statuses:** `open`, `in_progress`, `blocked`, `deferred`, `closed`. There is no rework
  status. A rework cycle stays `in_progress`, with a failed gate result and a comment.
- **Ready set:** each record that is not closed or deferred, has no open blocker and has
  no children. An `in_progress` record is in it.
- **Folded record:** `record`, `status`, `fields`, `comments`, `dates` (`created`,
  `updated`, `closed`, derived from the events), `max_seq`, `tombstoned`, `totals`,
  `dependencies`, `dependents`. The two edge keys are always present, and each edge names
  its type and the status of the other record.
- **Ids:** `<prefix>-<code>`, with one hyphen. The commit hook refuses a slug id with more
  hyphens. Let the tracker make the id.
- **Priority:** 0 critical to 4 backlog, default 2. Use 0 and 1 only for release-blocking
  or next work.
- **Types:** the harness work types are `bug`, `chore`, `epic`, `feature`, `task`; the default is `task`. The field accepts
  any string, but the loop cannot classify another type. File a document, a question or a
  spike as `task`.
- A lane builds only the leaf types `bug`, `chore`, `task`; an `epic` or a `feature`
  splits into children. Show hierarchy with a `parent-child` edge, not a new type.
