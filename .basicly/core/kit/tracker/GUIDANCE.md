---
name: work-tracker
description: Use the append-only work tracker as this repository's issue tracker — read what is ready, file and close records, record dependencies, and reference an id from a commit. Use when planning work, deciding what to do next, filing or closing an issue, or preparing a commit that must name one.
---

# The work tracker

**An append-only event ledger under `.basicly/ledger/`, committed with the code.** Records
are events, never rows edited in place, which is why two people or two agents working the
same backlog in parallel do not conflict. There is no server, no database and no binary to
install.

## Why it is append-only, and what that buys you

A tracker whose file is rewritten on every change conflicts the moment two branches touch
the backlog, and resolving it by hand risks losing a record. Here every write appends one
event to `events-*.jsonl`, and the install declares `merge=union` on that glob, so two
branches that each append merge clean and keep both events. State is *folded* from the log,
so the fold is the same whichever branch merged first.

That is the reason to prefer it, and it only holds if the git attribute is present. Check
with `basicly-tracker status` if a merge ever conflicts on the log.

## Read before you write

Every subcommand takes the repository directory as its first argument.

```sh
python3 .basicly/kit/tracker/cli.py ready .        # what is workable now, ranked
python3 .basicly/kit/tracker/cli.py blocked .      # what is waiting, and on what
python3 .basicly/kit/tracker/cli.py stats .        # counts by status
python3 .basicly/kit/tracker/cli.py show . <id>    # one record in full
python3 .basicly/kit/tracker/cli.py list .         # every record
```

`ready` is the one to start from: it excludes anything blocked by an open dependency and
ranks what is left, so the top row is the next thing to do. Read it before proposing work
rather than inventing a task.

## Write

```sh
python3 .basicly/kit/tracker/cli.py create . --prefix <p> --title "<what>" \
    --description "<the trigger>" --acceptance "<how it is checked>" --requirements "<the standard>"
python3 .basicly/kit/tracker/cli.py update . <id> --status in_progress
python3 .basicly/kit/tracker/cli.py comment . <id> "<what you learned>"
python3 .basicly/kit/tracker/cli.py dep . <id> <the-id-it-waits-on>
python3 .basicly/kit/tracker/cli.py close . <id> --reason "<what shipped, and the evidence>"
python3 .basicly/kit/tracker/cli.py child . <parent-id> --title "<a piece of it>"
```

Run `cli.py <verb> --help` for the exact flags; they are checked and a wrong one is refused
by name rather than ignored.

## Check the log itself

```sh
python3 .basicly/kit/tracker/cli.py fsck .            # exit 0 clean, 1 stale derivative, 2 broken
python3 .basicly/kit/tracker/cli.py fsck . --rebuild  # write the derivatives again first
```

The log is the truth and everything else is derived from it, which is only worth saying if
you can check it. Run this after a merge you are unsure about, or when a query answers
something that surprises you. A finding names the record and the reason; a broken log is
repaired by appending a corrective event, never by editing a line.

## Show a human where the work stands

```sh
python3 .basicly/kit/tracker/cli.py board . --out tracker-board.html
```

One self-contained page: the counts, the ranked ready set, what is blocked and what holds
it, a dependency drawing, and every record with what it still owes. No server and no
network — it is a file, and nothing on it updates until you run the command again. Write
it when someone asks what the state of the work is, rather than pasting JSON at them.

## Shape a record before you build against it

A record is **shaped** when it carries three things: a trigger in either story voice, the
acceptance criteria a check is derived from, and the requirements validation judges the
built thing against. Every write prints what the record still `owed`, and the gate refuses
one that is not shaped:

```sh
python3 .basicly/kit/tracker/cli.py dor . <id>     # exit 0 ready, exit 1 with what is missing
```

Run it before you start work, not after. The three sections are what you verify and
validate against; without them you are checking the code against your own reading of a
title, which is the failure this tracker exists to stop.

State the trigger as a situation — *"When <situation>, I want to <motivation>, so I can
<outcome>."* — or as a persona — *"As a <persona>, I want <goal>, so that <benefit>."* A
persona is never required: where a situation triggers the work and nobody in particular
wants it, inventing one is the defect. A placeholder counts as absent, so pasting either
template unfilled does not satisfy the gate.

`--acceptance` and `--requirements` are the direct route. A `## Acceptance Criteria` or
`## Requirements` section of dash-space bullets in the description counts too, so a record
written as prose stays valid.

**`ready` is not the gate.** It offers every unblocked record, shaped or not; `dor` is what
refuses. Read `ready` to choose, then run `dor` before you build.

## How to use it well

- **Claim before you build.** Set the record to in-progress so a second agent reading
  `ready` does not pick up the same thing.
- **A close reason is evidence, not a summary.** Name what shipped, what was run, and the
  number it produced. The reason is the permanent record; the diff is not searchable.
- **Put a finding on the record, not in a comment in the code.** The ledger is where a
  measurement stays true and stays attributable.
- **Reference the id in the commit message.** That is the only link between a change and
  why it was made.
- **Shape it as you file it.** `create` takes the three sections; adding them later costs
  a second write and the record is unusable in between.
- **File the thing you noticed.** A defect you found and did not file is one nobody else
  can see; `create` costs one command.

## What it will refuse

A record id that does not exist. A dependency edge that would make a cycle. A write to a
record the snapshot says is already closed, unless you say so deliberately. Each refusal
names the reason; read it rather than working around it.
