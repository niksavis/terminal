---
name: work-tracker
description: Use the append-only work tracker as this repository's issue tracker. Use when you plan work, choose what to do next, file, refine or close a record, or write a commit that must name a record id.
---

# The work tracker

The tracker is an append-only event ledger in `.basicly/ledger/`, committed with the code.
Every command takes the ledger directory as its first argument and prints one JSON object.
`.basicly/kit/tracker/REFERENCE.md` lists every command with one example.

## Rules

- **Many people share this tracker. Never take a story that someone holds.** `ready` names
  the holder of each reserved story. `assign` and `claim` refuse a held story and name the
  holder; `--take` is for an agreed handover only.
- **Reserve a story before you plan it, and push at once.** Run `assign` when you plan to
  work on a story, even days ahead, then commit and push the ledger. Others see a
  reservation only after they pull. Run `claim` when you start, and `unassign` when you
  drop it.
- **Read `ready` before you propose work.** Take the top row that nobody holds. Do not
  invent a task.
- **Run `dor` before you build.** `ready` leaves out a record labelled `refine` and a new
  record that fails `dor`, but it keeps an older unshaped record. `dor` refuses a record
  that has no trigger, acceptance criteria or requirements.
- **Criteria and requirements are fields.** Pass them as `--acceptance` and
  `--requirements`. A description that holds either heading is refused.
- **A close reason is evidence.** Name what shipped, the command you ran and its result.
- **Put a finding on the record**, not in a code comment.
- **Name the record id in the commit message.** It is the only link from a change to its
  reason.
- **Claim a record before you change code for it.** The `commit-msg` hook refuses a commit
  that changes files outside the ledger unless you hold a record it names in progress (or
  closed). Filing and closing commits that touch only the ledger pass.
- **File what you notice.** A defect that you do not file is invisible to everyone else.

## Read

```sh
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger        # workable now, ranked
python3 .basicly/kit/tracker/cli.py blocked .basicly/ledger      # waiting, and on what
python3 .basicly/kit/tracker/cli.py show .basicly/ledger <id>    # one record, its edges and dates
python3 .basicly/kit/tracker/cli.py dor .basicly/ledger <id>     # exit 0 shaped, exit 1 with what is missing
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger --mine # the stories you hold
```

A `holder` marked `stale` had no event for `stale_days` (14 by default); ask the holder
before you take it. A story marked `contested` was reserved by two people on different
branches; the two agree who keeps it, then run `resolve` to keep the current holder, or
`claim --take` to change it.

## Write

```sh
python3 .basicly/kit/tracker/cli.py create .basicly/ledger --prefix <p> --title "<what>" \
    --description "<the trigger>" --acceptance "<how it is checked>" --requirements "<the standard>"
python3 .basicly/kit/tracker/cli.py assign .basicly/ledger <id>                 # reserve it for you
python3 .basicly/kit/tracker/cli.py claim .basicly/ledger <id>                  # reserve it and start
python3 .basicly/kit/tracker/cli.py unassign .basicly/ledger <id>               # give it back
python3 .basicly/kit/tracker/cli.py comment .basicly/ledger <id> "<what you learned>"
python3 .basicly/kit/tracker/cli.py dep .basicly/ledger <id> <the-id-it-waits-on>
python3 .basicly/kit/tracker/cli.py child .basicly/ledger <parent-id> --title "<a piece of it>"
python3 .basicly/kit/tracker/cli.py close .basicly/ledger <id> --reason "<what shipped, and the evidence>"
```

## Shape a record

A shaped record carries three things:

1. **A trigger** in the description, in one of two voices. Situation: "When <situation>, I
   want to <motivation>, so I can <outcome>." Persona: "As a <persona>, I want <goal>, so
   that <benefit>." Do not invent a persona when a situation triggers the work.
2. **Acceptance criteria** as `--acceptance`. Write one bullet per check: "When <event>, the
   <system> shall <response>."
3. **Requirements** as `--requirements`. Name the standard that the result must obey, not
   the method.

A placeholder counts as absent. One record is one change that a person can see. A record
that needs more than one session is two records: split it with `child`.

`scaffold --type <type>` prints what a record of that type must carry. A `template.json`
beside the log adds sections (`extend`) or replaces them (`override`), for all records or
for one `issue_type`. A field named after a section, such as `--field risks="<text>"`,
satisfies it.

## Refine a record

A person writes or edits a story, often in the served page. The page adds the label
`refine`. The record is not ready to build until an agent does a refinement pass:

1. Run `refine` to list the open records that carry the label or fail `dor`.
2. For each record, read it with `show` and rewrite it with `update`: the trigger, the
   acceptance criteria, the requirements, the type, the priority and the `dep` edges.
3. Run `dor`. When it passes, remove the label: `update <id> --remove-label refine`. You
   may fill the missing fields and remove the label in the same `update`.

Only an agent removes the label, and only when nothing is owed. The kit reads the writer
class from `BR_AGENT_NAME` or `AI_AGENT` (set it to your agent's name), or from
`CLAUDECODE=1`. A person's attempt is refused. While a record carries the label or fails
`dor`, `claim` and `update --status in_progress` are refused; `assign` still reserves it.

Keep the intent of the person. When the intent is unclear, add a comment with the question
and leave the label on.

## What it refuses

Every refusal exits 1, names the reason and the fix, and writes nothing. Read it and fix the
cause. It refuses:

- a record id that the ledger does not hold, and an edge that makes a cycle;
- a status outside `open`, `in_progress`, `blocked`, `deferred`, `closed`;
- a priority outside 0 (critical) to 4 (backlog), and a `close` without `--reason`;
- a field that no code reads, an import-history field, or a derived date. `fields` prints
  each field, its role and its reader;
- a directory that is not a ledger, and a malformed `template.json`;
- `claim` or a move to `in_progress` on a record that carries `refine` or fails `dor`, and
  a person's removal of `refine`;
- a code commit that names no record you hold in progress.

## Show a person the state

```sh
python3 .basicly/kit/tracker/cli.py board .basicly/ledger --out tracker-board.html
```

`board` writes one static page. The optional board kit serves a live page and an HTTP API
where a person reads, creates and edits records: see the `tracker-board` skill.

## Merges and the log

- A write appends to `pending-<branch>.jsonl`, and `merge=union` in `.gitattributes` keeps
  both sides of a merge. A merge needs nothing from you. If a merge conflicts on the log,
  run `basicly-tracker status`: the attribute is missing.
- `fsck` checks the log: exit 0 clean, 1 stale derivative, 2 broken. Two writers on one
  record are a warning. When they set one value differently, `fsck` names both values:
  keep the current one with `resolve`, or choose with `update`. Never edit a line.
- `compact` folds the shards into the trunk log. Run it on the default branch as its own
  pull request. Use `init --fold-on-merge` only where one writer pushes straight to the
  default branch, because two pull requests that each carry a fold conflict.
- An event's `actor` is `agent:<name>` or `operator`. It never names a person. To find the
  person, ask git: `git log -S'<record-id>' -- .basicly/ledger`.
