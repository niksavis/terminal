# Tracker kit command reference

Ledger-form commands take the ledger directory, `.basicly/ledger`, as their first argument and
prints one JSON object with a `schema` field. `cli.py <command> --help` lists every flag.
The examples use `acme` as the id prefix and `acme-a1b2` as a record id.

## Coding agents

The standalone package ships agent skills, a plugin exporter and an MCP stdio adapter.
The basicly harness ships the same adapter with its tracker kit.
Install the standalone tool and skills for the user by default.
Use `init --sandbox` for the optional repository bundle.

```sh
basicly-tracker init --user
basicly-tracker mcp --repository REPOSITORY-ROOT
```

The adapter binds its repository at startup.
It advertises named tools and typed inputs through `tools/list`.
Calls use the existing tracker admission and canonical ownership rules.
Arguments cannot override the repository, vault, prefix or session identity.
Reconnect after changing `.basicly-tracker.toml`.

Set `BASICLY_TRACKER_SESSION` separately for each coding agent session. When it is unset, the kit uses `ORCH_SESSION_ID`, else `CLAUDE_CODE_SESSION_ID`, so a claim and the commit-msg hook of one Claude Code session name the same session.
Its tools and Git hooks must inherit that same value.
Choose the human-readable holder through `BASICLY_HOLDER` or `git config basicly.holder`.
Never persist one shared session identity for concurrent agents.
Only a settled successful claim authorizes work.
Then update the record to `in_progress` through the tracker.
Confirm observed evidence before closing.
Inspect the command's exit code, pending state and refusal report after every tool call.

The [standalone installation guide](https://github.com/niksavis/basicly/tree/main/packages/basicly-tracker) gives client registration commands.

## Configure

### config

Every tracker setting, with its value, its `source` and its `home`. The source is
`default`, `ledger file`, `env <NAME>`, `git config <key>` or `git hook post-merge`.

| Setting | Home |
| --- | --- |
| `prefix`, `stale_days`, `mode`, `sections`, `types` | `template.json` in the ledger, committed with it |
| `holder` | `git config basicly.holder`; `BASICLY_HOLDER` overrides it for one shell |
| `fold_on_merge` | the read-only post-merge reminder that `init --fold-on-merge` writes |
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

### Vault repositories

When `.basicly-tracker.toml` configures a vault, ordinary writes validate against its view
and queue carried ledger events beside the clone. They write no local ledger events.
The engine and standalone kit use the same admission and write adapter.

| Class | Forms | Vault behavior |
| --- | --- | --- |
| Ordinary writes | `create`, `child`, `update`, `close`, `comment`, `review`, `confirm`, `dep`, `undep`, `mark-ready` | Keep their ledger-form arguments and existing checks. |
| Canonical protocol | `claim`, `unassign` | Compatible ledger aliases use the native handler, report schema and exit codes. |
| Refused | `assign`, `resolve`, `acknowledge-loss`, `delete` | Write nothing and name a real remedy. |

Use native `claim RECORD-ID` to reserve work in the vault, then
`update .basicly/ledger RECORD-ID --status in_progress` to start it after its readiness checks.
Setting `assignee` directly is refused: ownership uses canonical claim and unassign events.
Ledger aliases refuse `claim --to`, `claim --take` and `unassign --by`; native session and
deadline options belong on the native form. `unassign --take` keeps its explicit meaning.
`assign` names `claim`; retired conflict/loss forms name `fsck --repair`; `delete` names
`close --resolution cancelled --reason ...` so the history remains.

Own pending events appear immediately in show, list, ready and the board, with
`sharing: pending` and a visible `pending` label. Another clone sees them after sharing.
Sharing deduplicates the event ids and clears that label. Reads retain the normal fetch age.
An unsettled pending claim does not grant ownership. A legacy raw native comment causes
an explicit counted read refusal naming `basicly-pvdo68d`; its projection is deferred.

```sh
python3 .basicly/kit/tracker/cli.py claim acme-a1b2 --vault path/to/vault.git
python3 .basicly/kit/tracker/cli.py update .basicly/ledger acme-a1b2 --status in_progress
python3 .basicly/kit/tracker/cli.py sync --urgent --vault path/to/vault.git
```

### create

Mint a record id and append its first events. `owed` in the output names what the record
still needs before `dor` passes. `--prefix` names the id prefix. Without it, `create` uses
the ledger's `prefix` setting, and refuses when the ledger sets none. `basicly-tracker init` sets that setting from the repository folder name when the ledger has none, and prints the command that changes it.

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
that nobody holds to `in_progress` also names you as its holder in ledger mode. Vault mode
requires your canonical claim first. `--if-seq N` refuses the
update when a field it writes changed after seq `N`, the `max_seq` that `show` gave you, so
an edit never silently replaces a newer one. Starting a child also starts each open parent,
and the output names those parents under `started_parents`. A comment or a field write on a
child never changes the status of its parent.

```sh
python3 .basicly/kit/tracker/cli.py update .basicly/ledger acme-a1b2 --status in_progress --add-label export
```

### comment

Append one comment. Text above 4,096 UTF-8 bytes after redaction is refused without
appending events. Shorten the note or link an artifact. Older clipped notes remain
readable with their original truncation metadata. Historical snapshot import preserves
full source prose, including notes above this limit.

```sh
python3 .basicly/kit/tracker/cli.py comment .basicly/ledger acme-a1b2 "The export drops a trailing newline."
```

With `--vault`, the comment validates the existing vault record and queues the same carried
note event as the ordinary form, beside its clone. Every
string in the event is redacted first: credential shapes and absolute paths become
`<redacted:rule>` markers. The command prints the queued count, the age of the oldest queued
event and what shares the queue next. Where `CI` or `BASICLY_TRACKER_EPHEMERAL` is set, it asks
for an immediate share. A queue line torn by a crash is cut back and reported.
The same text on one record is one note by content identity across sessions; a merged
native write reports `queued: 0` and `merged: true` with no additional note.

```sh
python3 .basicly/kit/tracker/cli.py comment acme-a1b2 --vault path/to/vault.git --text "The export drops a trailing newline."
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

In ledger mode, reserve a record and set it to `in_progress` in one write. It is
refused while the record carries the `refine` label or fails `dor`: an agent reviews it
first.

```sh
python3 .basicly/kit/tracker/cli.py claim .basicly/ledger acme-a1b2 --to alex
```

With `--vault`, `claim` reserves the record in the vault for this session (`--session`, else
`BASICLY_TRACKER_SESSION`) within one 30 s deadline that every git call shares. The first valid
claim in the vault wins. Exit codes: 0 the claim landed; 1 a session, a record id or a repair is
missing, and the fix is printed; 3 another session holds the record or won it, and the take
command is printed; 4 the deadline passed and the claim is unsettled, with `--wait` and
`--cancel` named; 5 the fetch gave no answer within 5 s, nothing is queued and the fetch command
is printed; 6 an internal error, with the log path and `sync`; 7 this session already holds it.

```sh
python3 .basicly/kit/tracker/cli.py claim acme-a1b2 --vault path/to/vault.git --session s1
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

Give a reserved record back. Only its holder can do this: `--by` names who gives it back
(default: `git config user.name`). Anyone else is refused with the holder's name. To release
another holder's record on purpose, pass `--take`, which the ledger records.

```sh
python3 .basicly/kit/tracker/cli.py unassign .basicly/ledger acme-a1b2
python3 .basicly/kit/tracker/cli.py unassign .basicly/ledger acme-a1b2 --take
```

### refine-sheet

Write a sheet of the open records that still miss acceptance criteria or a context: one block per
record with its id, title, context and its `acceptance:` list, which holds the record's criteria or
one empty line. The sheet goes inside the
repository's git folder, so it is never committed; `--out FILE` names another file. It refuses a
file that exists, and writes no file when no record owes criteria.
An import of a backlog names this command when records still need criteria.

```sh
python3 .basicly/kit/tracker/cli.py refine-sheet .basicly/ledger
```

### apply-sheet

Apply a filled refine sheet in one command. Each line that starts with a dash under `acceptance:` is
one criterion.
It refuses the whole sheet, naming each id, when an acceptance list is still empty or an id is not
in the ledger, or when the sheet names no record. A task, bug or chore with exactly one criterion
gets `size=small`. The report lists the records the sheet shaped, the ones the scheduler now ranks
ready (a blocked, deferred or parent record is shaped but not ready), and the records that still
owe a section, such as a review. A sheet that applied is removed.

```sh
python3 .basicly/kit/tracker/cli.py apply-sheet .basicly/ledger
```

### mark-ready

Record that an in_progress record is built and waits for delivery. Only its holder marks it
(`--to`, default: your holder name); a record that is not in_progress, held by someone else
or already marked is refused by name. `--again` marks it again after a change and `--clear`
removes the mark. The ready time is the time of the marking event:
`list --ready-for-delivery` prints it, oldest first.

```sh
python3 .basicly/kit/tracker/cli.py mark-ready .basicly/ledger acme-a1b2
python3 .basicly/kit/tracker/cli.py list .basicly/ledger --ready-for-delivery
```

### vault-check

Sort every commit on a vault's first-parent chain into a genesis, format, batch or archive
commit, or quarantine it with the rule it breaks. A quarantined commit voids only itself, and
nothing after a valid `ended` event counts. The vault is the backlog repository of design
version 8; this command only reads it.

```sh
python3 .basicly/kit/tracker/cli.py vault-check path/to/vault.git
```

### vault-show

Fold a vault's valid events and show one record: its holder (writer and session), its status,
every void event with the reason, and whether it holds an event kind this tracker cannot fold.
The first valid claim wins; only the holder can give a record back.

```sh
python3 .basicly/kit/tracker/cli.py vault-show path/to/vault.git acme-a1b2
```

### fetch

Clone a vault bare into the machine state folder the first time, then fetch its `main` into
`refs/remotes/origin/main`. One lock per clone makes a second fetch wait. A failed fetch is
retried once; after that the command shows the last fetched state and its age. After a fetch,
every new commit is sorted as `vault-check` does, quarantined commits are listed, and
`refs/basicly/seen` moves to the head. If the head no longer contains the seen commit, `seen`
stays and the report says `retracted`. The state folder is `--state`, else
`BASICLY_TRACKER_STATE`, else `basicly-tracker` under `XDG_STATE_HOME` (`LOCALAPPDATA` on
Windows), else under `~/.local/state`.

```sh
python3 .basicly/kit/tracker/cli.py fetch --vault path/to/vault.git
```

### status

Show the local vault state without a network call. The report gives the age of the last
fetch, each writer's last write, and the queued local events that the vault has not
received. `pending` names each queued event: its queue id, kind, record, carried event id
and age. `queued` is their count.

```sh
python3 .basicly/kit/tracker/cli.py status --vault path/to/vault.git
```

`hook EVENT --vault` runs from an agent hook and never fails the agent. `session-start` and
`prompt` fetch with a 3 s deadline at most every 20 s, then share only when this clone's bulk
slot is due (180 s after its last share). `stop` and `session-end` share the whole queue. A
person's write shares at once when the slot is due; otherwise a later `fetch` or write shares
it. `status --vault` makes no network call: it prints the fetch age, the last shared event and
its age per writer, the queued count and the oldest queued age, and any unrepaired retraction.

```sh
python3 .basicly/kit/tracker/cli.py hook stop --vault path/to/vault.git
python3 .basicly/kit/tracker/cli.py status --vault path/to/vault.git
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

A beads import also reads `issue_prefix` (br) or `issue-prefix` (bd) from
`.beads/config.yaml`. It sets the ledger prefix when the ledger has none, and it reports
both prefixes and changes neither when they differ.

### sync

Re-import the tracker that this ledger mirrors. `basicly-tracker init --mirror beads`
starts a mirror: it imports `.beads/issues.jsonl`, writes `mirror.json` in the ledger, and
installs no claim gate, because br stays the source of truth. `sync` imports new records,
comments, edges and every status change, so br wins for status. It reports the records
whose status changed, the records whose fields diverged, and the records br no longer
holds. It warns when `.beads/beads.db` is newer than the export, and names
`br sync --flush-only`. `init --end-mirror` ends the mirror and installs the claim gate.

```sh
python3 .basicly/kit/tracker/cli.py sync .basicly/ledger --dry-run
```

With `--vault`, `sync` shares the vault queue instead. It fetches, drops queued events the
vault already holds, appends the rest to this writer's segment as one commit on the fetched
head, and pushes it without force. A refused push fetches and rebuilds, at most 5 times; with
`--urgent` it retries until `--deadline` seconds pass. After a push, `refs/basicly/seen` moves
and the shared events leave the queue. If the vault holds a valid `ended` event, nothing is
pushed, the queue is kept, and the reason and successor are printed. A share that stops at any
step leaves each event in the vault once after the next `sync`.

```sh
python3 .basicly/kit/tracker/cli.py sync --vault path/to/vault.git
```

## Read

### ready

The ranked records that can be worked on now. It leaves out a record labelled `refine`,
a record created under the current rule that fails `dor`, and an `in_progress` record that no
one holds, which someone else may be working on. Each row names its `holder`
when someone has reserved it, with `stale` when the record had no event for `stale_days`
(14 by default, set in `template.json`) and `contested` when two people reserved it on
different branches. `--mine` lists only the records you hold.

```sh
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger --limit 10
```

### blocked

Each record that is not ready, and what holds it. An `in_progress` record that no one holds
shows `in_progress_elsewhere`: since when it is in progress, and the `claim` command that adopts
it.

```sh
python3 .basicly/kit/tracker/cli.py blocked .basicly/ledger
```

### stats

Counts by status, with the ready and blocked counts.

```sh
python3 .basicly/kit/tracker/cli.py stats .basicly/ledger
```

### commit-check

The check the `commit-msg` hook runs; you do not run it yourself. In local ledger mode it reads the commit
message file and the staged paths, and refuses a commit that changes files outside the
ledger unless the committer (`git config user.name`) holds a record the message names in
progress or closed. A ledger with no record yet passes, and the files a kit install manages
(`.basicly/kit/`, the tracker and board skills, `.gitignore`, `.gitattributes`) do not count,
so the install commit works.

With `.basicly-tracker.toml`, installed standalone and harness claim hooks use the native
vault protocol below. The bundled tracker kit supplies this capability without an engine.
The hooks verify the frozen `.basicly/ledger` file and its complete archive before checking claims.
The harness path scan and ledger fsck read the canonical project view, including local queued writes.
The fold hook preserves the frozen files. Harness landing refuses a lane that changes frozen
history or its vault binding. Preserve that lane and inspect its late events with
`migrate LEDGER --to-vault --preview` before importing them and rebasing onto the frozen destination.

With `--vault`, `commit-msg` checks the message file against the vault claims of this session
(`--session`, else `BASICLY_TRACKER_SESSION`, else `ORCH_SESSION_ID` or `CLAUDE_CODE_SESSION_ID`). It exits 1 when the message names no record id
and has no `Record: none` line, and prints the claim command and `Record: none`. A record id
is the `(id)` that ends the subject, or a `Record: <id>` line. When the session holds exactly
one claim, the hook adds the id in parentheses to the subject instead. Git-generated
`Merge`, `Revert "`, `fixup!` and `squash!` messages pass, and a revert or fixup takes the id
in the subject it repeats. A named record that this session does not hold, or whose claim has not reached the
vault, passes with a warning and the claim command. When a fetch older than 20 s fails, the
hook queues a local `miss` event for the record.

```sh
python3 .basicly/kit/tracker/cli.py commit-msg --vault path/to/vault.git .git/COMMIT_EDITMSG
```

### show

One record's folded state and its edges in both directions, each edge with the title of the
other record. It also names the `holder`, any unresolved `conflicts`, and a `comment_log`
that gives each comment with its writer class and time.

```sh
python3 .basicly/kit/tracker/cli.py show .basicly/ledger acme-a1b2 --view current
python3 .basicly/kit/tracker/cli.py show .basicly/ledger acme-a1b2 --view history --snapshot <snapshot_identity>
python3 .basicly/kit/tracker/cli.py show .basicly/ledger acme-a1b2
```

### list

Every record, filtered by `--status` and cut by `--limit`.

```sh
python3 .basicly/kit/tracker/cli.py list .basicly/ledger --status open --limit 20
```

With the basicly engine installed, a board can read every project in the configured vault:

```sh
basicly tracker list --json --all-projects
```

The response has `read_at` (UTC), `vault_head` (the captured published commit) and
`records`. Each record has `id`, `title`, `status`, `holder`, `priority`, `project` and
`ready`. A holder is `{ "writer": "...", "session": "..." }` or `null`; it comes from
the canonical claim, rather than a historical assignee field. Readiness uses each
project's template and the shared dependency graph. Own unshared records and changes
are included with `sharing: pending`; `vault_head` still names the published baseline.
The existing `--status`, `--query` and `--limit` filters also apply. A repository without
vault configuration refuses `--all-projects` and names `.basicly-tracker.toml`.

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

### migrate

Import a ledger, beads, br or beans backlog into a vault, or export one prefix. The steps, the
preview, the private map and the redaction rules are in [the vault migration guide](VAULT-MIGRATION.md).

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

With `--vault`, `fsck` reports the vault clone instead: the head, `refs/basicly/seen`, every
retracted ref and whether it is repaired, every quarantined commit with its rule, and the queue
size. When a fetched head no longer holds the commit `seen` named, the old tip is kept as
`refs/basicly/retracted/N` and every share is refused until a repair. `--repair` works from the
local clone only: your own lost lines go back in the queue as they were, other writers' lost
lines go in one `requeue` event that changes no holder, and each claim that no longer holds gets
a `claim-lost` event. Kept quarantine entries are processed the same way.
`--accept-rewrite HEAD --purge` accepts the fetched head and drops the retracted refs.
`reclone --vault` clones again and keeps `refs/basicly/*` and the writer id.

```sh
python3 .basicly/kit/tracker/cli.py fsck --vault path/to/vault.git --repair
python3 .basicly/kit/tracker/cli.py reclone --vault path/to/vault.git
```

### acknowledge-loss

Record proven unrecoverable history without inventing a missing event.
Pass the exact missing sequence set in ascending order. Repeat `--sequence`
and `--evidence` as needed. The reason and each historical reference must be nonempty.
The example requires a confirmed missing sequence 9 with later surviving history.
On healthy history, the command refuses with a nonzero exit and writes nothing.

```sh
python3 .basicly/kit/tracker/cli.py acknowledge-loss .basicly/ledger acme-a1b2 --sequence 9 --reason "Original content unavailable" --evidence "git:COMMIT"
```

The command appends a present-day artifact bound to the surviving history digest.
`fsck` retains a warning that the original content remains unknown.
Changed history, malformed acknowledgments, and new gaps still fail.

### shards

The pending writer shards the ledger holds.

```sh
python3 .basicly/kit/tracker/cli.py shards .basicly/ledger
```

### compact

Fold every pending shard into the trunk log. Run it on the default branch as its own
pull request. `init --fold-on-merge` reports this command after a merge; it never runs
compaction or creates a commit from a Git hook.
Compaction also removes byte-identical copies from trunk logs. It validates all
copies first and refuses differing stored bytes before changing any file.

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

## Review and confirmation

### review

`review <ledger> <id> --evidence '<JSON>'` records one planned command argv and expected
result per criterion. Explicit tasks, bugs and chores may submit `checks` only. The full
review also records six INVEST rationales and actual same-card comment `seq` references;
other or missing types require that form. `confirm <ledger> <id> --evidence '<JSON>'`
records exact matching argv, observed results and exit code 0 for every criterion.
`GUIDANCE.md` gives both review forms and the completion shape.
The tracker computes revisions and writer identities; these keys cannot be supplied.

### confirm

Confirmation uses the `confirm` command and the completion JSON shape in `GUIDANCE.md`.
Each check's `result` is what the command printed. `confirm` refuses a result that says the check has not run, such as `pending` or `will run after landing`.

`close <ledger> <id> --reason "<delivered outcome>"` defaults to completed and requires
current review and confirmation. `--resolution cancelled` records reasoned abandonment,
keeps history, and does not satisfy a blocking dependency. `stats` includes `by_resolution`.

## Vault push protection

The tracker installs a native Git pre-push guard in its private vault clones.
Standalone and harness installations use the same guard without another hook dependency.
The guard lives in Git metadata and adds no files to the vault history.
It checks every outgoing commit and allows only the vault main branch.
Unrelated files, invalid event envelopes, extra refs, deletion and history rewrites refuse before publication.
Normal code repositories keep their existing push behavior.

A manually cloned vault needs explicit protection.

```sh
basicly-tracker vault-protect --repository VAULT-CLONE
```

The harness ships the same command through its tracker kit.

```sh
python3 .basicly/core/kit/tracker/cli.py vault-protect --repository VAULT-CLONE
```

Installation preserves an unrelated hook and refuses rather than replacing it.
Installing again refreshes tracker-owned protection.
The guard keeps a private copy of its validator and still needs its selected Python runtime.
Direct vault format edits require reviewed maintenance and are refused by the normal guard.

This is local protection against mistakes.
Git does not copy hooks into new clones automatically.
A deliberately bypassed hook or an unprotected clone remains outside this protection.
Remote protection against deletion and history rewrites remains a separate host setting.
