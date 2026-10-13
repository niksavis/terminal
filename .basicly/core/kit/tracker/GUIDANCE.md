---
name: work-tracker
description: Use the append-only work tracker as this repository's issue tracker. Use when a task plans work, chooses what to do next, files, refines or closes a record, or writes a commit that must name a record id.
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
- **Run `dor` before you build.** `ready` leaves out every record labelled `refine` or
  failing `dor`. `dor` names missing card fields, INVEST rationales, conversation references and planned checks.
- **Criteria and requirements are fields.** Pass them as `--acceptance` and
  `--requirements`. A description that holds either heading is refused.
- **Confirm before completing.** Record actual results with `confirm`, then name the delivered
  outcome in `close --reason`. Use `--resolution cancelled` with an abandonment reason when
  work will not be built. Cancellation does not satisfy a dependency.
- **Put a finding on the record**, not in a code comment.
- **Name the record id in the commit message.** It is the only link from a change to its
  reason.
- **Claim a record before you change code for it.** The `commit-msg` hook refuses a commit
  that changes files outside the ledger unless you hold a record it names in progress (or
  closed). Filing and closing commits that touch only the ledger pass.
- **Stage the claim with its code.** The commit hook reads the Git index, not unsaved
  ledger changes. In a shared-ledger worktree, publish the claim on the base and update
  the lane from that committed base before committing its code.
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

Each trigger part needs text: the situation or persona, motivation or goal, and outcome
or benefit. Empty parts, punctuation alone, and placeholders such as `<outcome>`, `TODO`
or `TBD` cannot shape a trigger. Each criterion and requirement must be filled.

Capture a raw idea with `create --title` even when these parts are unknown. The reply names
what it owes. `ready` leaves it out, and `claim` refuses it until refinement fills the gaps.
One record is one change that a person can confirm.

`scaffold --type <type>` prints what a record of that type must carry. A `template.json`
beside the log adds sections (`extend`) or replaces them (`override`), for all records or
for one `issue_type`. A field named after a section, such as `--field risks="<text>"`,
satisfies it.

A record has one of six types: `task`, `bug`, `feature`, `chore`, `epic` or `research`. An
`epic` holds features, tasks, bugs, chores and research records. A `feature` holds tasks, bugs
and chores. A task, bug, chore or research record holds no children. `GET /api/v1` lists the
types as `record_types` and the allowed children as `child_types`.

## INVEST

Before an agent starts a card, review these six qualities and record a rationale for each
with `review --evidence`. Resolve a failed quality before claiming. The tracker enforces
recorded, filled evidence. It cannot prove that a rationale is semantically correct.

| Quality | Observable check | Action when it fails |
| --- | --- | --- |
| Independent | Read `show` and its dependencies. Can this change ship without an unfinished card? | Add a `dep` for real waiting work. Split coupled work with `child`. |
| Negotiable | Can the implementation change while the outcome and required standard stay true? | Discuss the constraint in a `comment`. Keep a required method only when the person confirms why. |
| Valuable | Does the outcome name an observable benefit to a person or system? | Ask who or what benefits. Keep the answer in the trigger. |
| Estimable | Can the agent name the scope, unknowns, and check from evidence it has read? | Record the missing fact in a `comment`. Leave `refine` until the fact is resolved. |
| Small | Does the card have one outcome that can be built and confirmed in one session? | Use `child` for each separately confirmable outcome. Preserve the parent intent. |
| Testable | Does each criterion name an input or event and an observable response? | Rewrite `--acceptance`. Name the demonstration or test and its expected result before building. |

`dor`, `ready` and `claim` require this recorded review, references to actual same-card
conversation comments, and a planned check for every criterion. A dependency can be valid
and still keep a reviewed card out of `ready`.

## Card, Conversation, Confirmation

Use all three parts of C3 throughout the card's life:

1. **Card:** capture the person's intent, then fill the trigger, acceptance criteria, and
   requirements with `update`. Run `show` to read the saved card. Keep scope and outcomes
   small enough to confirm independently.
2. **Conversation:** use `comment` for a question, its answer, an alternative, or an agreed
   constraint. Read the comments in `show` before rewriting intent. When a fact is missing,
   leave `refine` and ask the person. A saved comment records an answer; it does not grant
   permission or settle an unanswered question.
3. **Confirmation:** agree a command argv and expected result for every criterion before
   `claim`. After implementation, run those checks and exercise the result as a consumer.
   Use `confirm --evidence` to record each exact argv, its observed result and exit code 0.
   Close as completed only after every criterion is confirmed, with the delivered outcome
   in `--reason`. A comment alone does not satisfy completion confirmation.

Read `show` first. Its `comment_log` gives each comment's `seq`; its `process` report gives
stored review and confirmation evidence. `review` takes this JSON shape:

```json
{
  "invest": {
    "independent": "The save operation has no unfinished prerequisites.",
    "negotiable": "Storage may change while saved tasks remain readable.",
    "valuable": "A person can return to a captured task.",
    "estimable": "The existing save and show paths bound the change.",
    "small": "One saved title is the card's outcome.",
    "testable": "The saved title can be observed through show."
  },
  "conversation": [3],
  "checks": [{
    "criterion": "When a task is saved, show shall return its title.",
    "command": ["python3", "check_saved_title.py"],
    "expected": "The saved title appears in show."
  }]
}
```

Replace `3` with an actual same-card comment sequence and the check with your actual
criterion and planned argv. The tracker displays these commands; it does not execute them.
Every criterion must appear once. Pass the JSON as one argument:

```sh
python3 .basicly/kit/tracker/cli.py review .basicly/ledger <id> --evidence '<review JSON>'
python3 .basicly/kit/tracker/cli.py claim .basicly/ledger <id>
```

After running the agreed check, `confirm` takes the following shape. Record only output
you actually observed; preserve a failed result in a comment and keep the card open.

```json
{
  "checks": [{
    "criterion": "When a task is saved, show shall return its title.",
    "command": ["python3", "check_saved_title.py"],
    "result": "The saved title appeared in show.",
    "exit_code": 0
  }]
}
```

```sh
python3 .basicly/kit/tracker/cli.py confirm .basicly/ledger <id> --evidence '<confirmation JSON>'
python3 .basicly/kit/tracker/cli.py close .basicly/ledger <id> --reason "Saved tasks can be read again."
python3 .basicly/kit/tracker/cli.py close .basicly/ledger <id> --resolution cancelled --reason "This work is no longer needed."
```

The tracker computes the review revision and generic writer identity itself. Editing the
title, trigger, criteria, requirements, type, dependency edges or a direct dependency
contract invalidates review and confirmation. Effective template headings and required
custom field values also bind the review. Record updated evidence before the next claim
or completed close. Holder
and status changes preserve the review. Existing closed history remains readable, while
legacy open cards need current evidence. `stats` reports closed dispositions separately.

## Refine a record

A person writes or edits a story, often in the served page. The page adds the label
`refine`. The record is not ready to build until an agent does a refinement pass:

1. Run `refine` to list the open records that carry the label or fail `dor`.
2. For each record, read it with `show` and rewrite it with `update`: the trigger, the
   acceptance criteria, the requirements, the type, the priority and the `dep` edges.
3. Record `review` evidence, then run `dor`. When it passes, remove the label with
   `update <id> --remove-label refine`. Editing the reviewed fields requires a new review
   before removing the label.

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
- a type outside the six, and a parent and child whose types the hierarchy does not allow;
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
