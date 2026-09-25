# Tracker kit command reference

Every command takes the ledger directory, `.basicly/ledger`, as its first argument and
prints one JSON object with a `schema` field. `cli.py <command> --help` lists every flag.
The examples use `acme` as the id prefix and `acme-a1b2` as a record id.

## Configure

### config

Every tracker setting, with its value, its `source` and its `home`. The source is
`default`, `ledger file`, `env <NAME>`, `git config <key>` or `git hook post-merge`.

| Setting | Home |
| --- | --- |
| `prefix`, `stale_days`, `mode`, `sections`, `types` | `template.json` in the ledger, committed with it |
| `holder` | `git config basicly.holder`; `BASICLY_HOLDER` overrides it for one shell |
| `fold_on_merge` | the post-merge git hook that `init --fold-on-merge` writes |
| `pin` | `.kit-version` in the ledger, which `init` and `update` write |

```sh
python3 .basicly/kit/tracker/cli.py config .basicly/ledger
```

`config <ledger> set NAME VALUE` writes one setting whose home is `template.json`. A list or a
number is read as JSON. The same rules as a hand-written `template.json` refuse a wrong
value, and nothing is written. An unknown name is refused with the list of known names. A
setting with another home is refused with the command that sets it, for example
`git config basicly.holder alex`.

```sh
python3 .basicly/kit/tracker/cli.py config .basicly/ledger set prefix acme
```

## Write

### create

Mint a record id and append its first events. `owed` in the output names what the record
still needs before `dor` passes. `--prefix` names the id prefix. Without it, `create` uses
the ledger's `prefix` setting, and refuses when the ledger sets none.

```sh
python3 .basicly/kit/tracker/cli.py create .basicly/ledger --prefix acme --title "Keep comments on export" --description "When an export holds a comment, I want it kept, so I can import it back." --acceptance "- The importer shall keep every comment line" --requirements "- Standard library only"
```

### child

Mint the next child id under a parent and record the parent-child edge.

```sh
python3 .basicly/kit/tracker/cli.py child .basicly/ledger acme-a1b2 --title "Parse multi-line comments"
```

### update

Set fields, the status or labels. `--add-label` and `--remove-label` repeat. Moving a story
that nobody holds to `in_progress` also names you as its holder. `--if-seq N` refuses the
update when a field it writes changed after seq `N`, the `max_seq` that `show` gave you, so
an edit never silently replaces a newer one.

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
when omitted: `blocks`, `parent-child`, `related` or `discovered-from`. An edge that would
make a cycle, an edge the record already has, and a `blocks` edge on a closed record are
refused.

```sh
python3 .basicly/kit/tracker/cli.py dep .basicly/ledger acme-a1b2 acme-c3d4
```

### undep

Retract an edge the first record holds on the second, as one appended event. An edge the
record does not hold, and a `parent-child` edge, are refused.

```sh
python3 .basicly/kit/tracker/cli.py undep .basicly/ledger acme-a1b2 acme-c3d4
```

### close

Move one or more records to `closed`. The reason is the permanent record of what shipped.

```sh
python3 .basicly/kit/tracker/cli.py close .basicly/ledger acme-a1b2 --reason "Shipped the importer fix; the round-trip test passes"
```

### assign

Reserve a record for a person without changing its status, so that others see it is taken.
The holder is `--to`, or else the name you choose with `BASICLY_HOLDER` or `git config basicly.holder`, or else `git config user.name`. The ledger records that name, so choose a pseudonym when your git name must not be committed. A record that someone else holds is
refused with the holder's name; `--take` takes it on purpose, and the ledger records that.

```sh
python3 .basicly/kit/tracker/cli.py assign .basicly/ledger acme-a1b2 --to alex
```

### claim

Reserve a record and set it to `in_progress` in one write, when you start the work. It is
refused while the record carries the `refine` label or fails `dor`: an agent reviews it
first.

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

`--from beans` reads a beans backlog instead. Name the repository root that holds
`.beans`, or the `.beans` folder. Each bean becomes one record, and a bean in
`.beans/archive` is closed. The parent becomes a `parent-child` edge, `blocking` and
`blocked_by` become `blocks` edges, and the tags become labels. A frontmatter form or a
status, type or priority that the reader does not know refuses the file by name, and
no bean of the batch is imported.

```sh
python3 .basicly/kit/tracker/cli.py import .basicly/ledger issues.jsonl --dry-run
```

`basicly-tracker init` and `update` look for a backlog to import. They read files only
and never run `bd`, `br` or `beans`:

| Found | What init does |
| --- | --- |
| `.beads/issues.jsonl` | names it with its record count and offers the import |
| `.beads/dolt` or `.beads/embeddeddolt`, and no `issues.jsonl` | says to run `bd export -o .beads/issues.jsonl` first |
| a `.beans` folder of beans | names it with its bean count and offers the import |
| `.beans.yml`, and no bean under `.beans` | says to import the folder that `.beans.yml` sets by name |

At a terminal, init prints a dry-run summary and asks once. It imports only on `y` or
`yes`. With no terminal, as when an agent runs it, init imports nothing and prints the
command that does: `basicly-tracker init --import beads` or
`basicly-tracker init --import beans`. `--import` refuses a source that the repository
does not hold, and nothing is written. An imported record has no Trigger, Acceptance
Criteria or Requirements, so it lands in `refine` and `ready` shows 0 until each record
is shaped. `refine` lists them. `basicly install` makes the same offer with no prompt,
and names `basicly tracker import` instead.

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

### commit-check

The check the `commit-msg` hook runs; you do not run it yourself. It reads the commit
message file and the staged paths, and refuses a commit that changes files outside the
ledger unless the committer (`git config user.name`) holds a record the message names in
progress or closed. A ledger with no record yet passes, and the files a kit install manages
(`.basicly/kit/`, the tracker and board skills, `.gitignore`, `.gitattributes`) do not count,
so the install commit works.

### show

One record's folded state and its edges in both directions, each edge with the title of the
other record. It also names the `holder`, any unresolved `conflicts`, and a `comment_log`
that gives each comment with its writer class and time.

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
type, priority, edges) and removes the label with `update --remove-label refine`. Only an
agent writer removes it, and only when `dor` passes.

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
