# Tracker kit command reference

Every command takes the ledger directory, `.basicly/ledger`, as its first argument and
prints one JSON object with a `schema` field. `cli.py <command> --help` lists every flag.
The examples use `acme` as the id prefix and `acme-a1b2` as a record id.

## Write

### create

Mint a record id and append its first events. `owed` in the output names what the record
still needs before `dor` passes.

```sh
python3 .basicly/kit/tracker/cli.py create .basicly/ledger --prefix acme --title "Keep comments on export" --description "When an export holds a comment, I want it kept, so I can import it back." --acceptance "- The importer shall keep every comment line" --requirements "- Standard library only"
```

### child

Mint the next child id under a parent and record the parent-child edge.

```sh
python3 .basicly/kit/tracker/cli.py child .basicly/ledger acme-a1b2 --title "Parse multi-line comments"
```

### update

Set fields, the status or labels. `--add-label` and `--remove-label` repeat.

```sh
python3 .basicly/kit/tracker/cli.py update .basicly/ledger acme-a1b2 --status in_progress --add-label export
```

### comment

Append one comment.

```sh
python3 .basicly/kit/tracker/cli.py comment .basicly/ledger acme-a1b2 "The export drops a trailing newline."
```

### dep

Record that the first record waits on the second. `--type` sets the edge type, `blocks`
when omitted. An edge that would make a cycle is refused.

```sh
python3 .basicly/kit/tracker/cli.py dep .basicly/ledger acme-a1b2 acme-c3d4
```

### close

Move one or more records to `closed`. The reason is the permanent record of what shipped.

```sh
python3 .basicly/kit/tracker/cli.py close .basicly/ledger acme-a1b2 --reason "Shipped the importer fix; the round-trip test passes"
```

### assign

Reserve a record for a person without changing its status, so that others see it is taken.
The holder is `--to`, or else `git config user.name`. A record that someone else holds is
refused with the holder's name; `--take` takes it on purpose, and the ledger records that.

```sh
python3 .basicly/kit/tracker/cli.py assign .basicly/ledger acme-a1b2 --to alex
```

### claim

Reserve a record and set it to `in_progress` in one write, when you start the work.

```sh
python3 .basicly/kit/tracker/cli.py claim .basicly/ledger acme-a1b2 --to alex
```

### resolve

Two branches can write the same record, and the merge keeps both events. When they set one
status or one field to different values, `fsck` fails with `conflicting-fork` and names the
values, and `show` lists them under `conflicts`. `resolve` keeps the current value by
appending one event. To keep the other value, use `update` instead. A fork that sets nothing
in conflict, such as two comments, is only a warning.

```sh
python3 .basicly/kit/tracker/cli.py resolve .basicly/ledger acme-a1b2
```

### unassign

Give a reserved record back.

```sh
python3 .basicly/kit/tracker/cli.py unassign .basicly/ledger acme-a1b2
```

### delete

Tombstone a record. Its id is never reused.

```sh
python3 .basicly/kit/tracker/cli.py delete .basicly/ledger acme-a1b2
```

### import

Bring a JSONL export from another tracker across, one record per line. `--dry-run`
reports the same plan and writes nothing.

```sh
python3 .basicly/kit/tracker/cli.py import .basicly/ledger issues.jsonl --dry-run
```

## Read

### ready

The ranked records that can be worked on now. It leaves out a record labelled `refine`,
and a record created under the current rule that fails `dor`. Each row names its `holder`
when someone has reserved it, with `stale` when the record had no event for `stale_days`
(14 by default, set in `template.json`) and `contested` when two people reserved it on
different branches. `--mine` lists only the records you hold.

```sh
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger --limit 10
```

### blocked

Each record that is not ready, and what holds it.

```sh
python3 .basicly/kit/tracker/cli.py blocked .basicly/ledger
```

### stats

Counts by status, with the ready and blocked counts.

```sh
python3 .basicly/kit/tracker/cli.py stats .basicly/ledger
```

### show

One record's folded state and its edges in both directions.

```sh
python3 .basicly/kit/tracker/cli.py show .basicly/ledger acme-a1b2
```

### list

Every record, filtered by `--status` and cut by `--limit`.

```sh
python3 .basicly/kit/tracker/cli.py list .basicly/ledger --status open --limit 20
```

## Shape

### dor

The definition of ready. Exit 0 when the record carries everything the rule requires,
exit 1 with what is missing and how to add it.

```sh
python3 .basicly/kit/tracker/cli.py dor .basicly/ledger acme-a1b2
```

### scaffold

The headings, description skeleton and flags a record of one type must carry, read from
the ledger's `template.json` when there is one.

```sh
python3 .basicly/kit/tracker/cli.py scaffold .basicly/ledger --type bug
```

### fields

Each record field, its role and the code or person that reads it. A write of a field
that is not in the table, or of an import-history field, is refused. `show` prints the
derived `dates` (created, updated, closed) computed from the event times.

```sh
python3 .basicly/kit/tracker/cli.py fields .basicly/ledger
```

### refine

The open records a refinement pass owes: each one carries the `refine` label or fails
`dor`. A person writes or edits a story, and the board page adds the label. An agent then
rewrites the record with the full fields (trigger, acceptance criteria, requirements,
type, priority, edges) and removes the label with `update --remove-label refine`.

```sh
python3 .basicly/kit/tracker/cli.py refine .basicly/ledger
```

### migrate-fields

Move the acceptance criteria and the requirements of each open record from a description
section into the typed field, when the field is empty. It appends events and edits no line.
A second run appends nothing.

```sh
python3 .basicly/kit/tracker/cli.py migrate-fields .basicly/ledger
```

## Keep the log healthy

### fsck

Fold the whole log and report anything broken. Exit 0 clean, 1 stale derivative, 2 broken.
`--rebuild` writes the derived files again first.

```sh
python3 .basicly/kit/tracker/cli.py fsck .basicly/ledger
```

### shards

The pending writer shards the ledger holds.

```sh
python3 .basicly/kit/tracker/cli.py shards .basicly/ledger
```

### compact

Fold every pending shard into the trunk log. Run it on the default branch as its own
pull request; `init --fold-on-merge` runs it after a merge where one writer pushes there.

```sh
python3 .basicly/kit/tracker/cli.py compact .basicly/ledger
```

## Show

### board

Write one self-contained HTML page: the counts, the ready set, what is blocked, a
dependency drawing and every record with what it still owes.

```sh
python3 .basicly/kit/tracker/cli.py board .basicly/ledger --out tracker-board.html
```
