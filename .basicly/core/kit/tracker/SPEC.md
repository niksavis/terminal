# The tracker kit's specification

This file states what the tracker store guarantees to a reader who has only the kit. Nothing
here depends on a document outside the kit, because a consumer who installs the kit receives
no other document.

## How to read the section numbers

The kit's modules cite their requirements as bare section marks, and a gate checks each mark
against a heading below. So the numbers stay as they are, and a gap in the numbers is
intentional.

Two rules control the content:

- A rule that the kit implements is stated as a rule. The rule carries the reason that the
  code cannot show, such as a measured threshold or the defect that a guard prevents.
- The code is the authority. This file is the contract that the code must meet, not a
  second description of the code.

## 3. Install

Install the kit with `uvx`. The installer also declares the git attributes that the ledger
needs, so a hand copy is not equivalent.

```console
$ uvx --from git+https://github.com/niksavis/basicly#subdirectory=packages/basicly-tracker basicly-tracker init
tracker: added to .gitattributes: events-*.jsonl -text merge=union
tracker: added to .gitattributes: pending-*.jsonl -text merge=union
tracker: added to .gitignore: .basicly/ledger/snapshot.jsonl
tracker: added to .gitignore: .basicly/ledger/checkpoint-*.jsonl
tracker: added to .gitignore: .basicly/kit/tracker/__pycache__/
tracker: 31 file(s) written, 0 unchanged, in .basicly/kit/tracker
tracker: wrote the skill to .claude/skills/tracker/SKILL.md
tracker: wrote the skill to .agents/skills/tracker/SKILL.md
```

- The installer writes the attributes before the first kit file. If it cannot write them,
  it refuses and leaves nothing behind. Without `merge=union`, two branches that each append
  an event conflict.
- The installer reads the globs from `events.LOG_GLOB`, `events.PENDING_GLOB` and
  `snapshot.DERIVED_PATTERNS`. It never spells them a second time (§9.4).
- `init` creates the ledger directory, `.basicly/ledger`.
- `update` vendors the kit again and reports what changed. `status` tells whether the
  installed copy and its rules are current. `uninstall` removes exactly what `init` wrote.
- `init` writes the kit's skill into `.claude/skills/tracker/` and `.agents/skills/tracker/`.
  The skill tells an agent that the kit exists and when to use it.
- `--with-instructions` also writes a short always-on block into each of `CLAUDE.md`,
  `.claude/CLAUDE.md`, `AGENTS.md` and `.github/copilot-instructions.md` that exists. The
  block sits in a marked region. A second run does not duplicate it, and `uninstall` removes
  it byte for byte. Without the flag, the installer only tells where the block is, because
  an installer must not edit an instruction file unasked.
- `--fold-on-merge` wires a `post-merge` git hook that runs `compact` on the default branch
  and commits the result (§4.0). Without it, the installer says that no fold is wired.

After the install, plain `python3` runs the kit, with no `uvx`, no network and nothing on
`PATH`. Each subcommand takes the ledger directory as its first argument. The command refuses
a repository root, or a directory that holds no ledger, instead of reporting an empty
backlog:

```console
$ python3 .basicly/kit/tracker/cli.py create .basicly/ledger --prefix demo --title "try the tracker"
{
  "blocking": ["## Trigger", "## Acceptance Criteria", "## Requirements"],
  "events": ["demo-qeom#ev-cdc2f647a4", "demo-qeom#ev-04bc122532"],
  "owed": ["## Trigger", "## Acceptance Criteria", "## Requirements"],
  "record": "demo-qeom",
  "remedy": "state the trigger in either voice - ...",
  "schema": "basicly.tracker.create.v2"
}
$ python3 .basicly/kit/tracker/cli.py ready .basicly/ledger
{
  "count": 1,
  "records": [{"rank": 1, "record": "demo-qeom", "score": 2000, "title": "try the tracker"}],
  "schema": "basicly.scheduler.v1",
  "sort": "priority ASC, dependents DESC, id ASC"
}
```

Each write reports the sections of the definition of ready that the record still owes, and
`dor` refuses a record that cannot be verified against.

A hand copy of the files still runs, because the kit imports only the standard library. But
a hand copy does not write the git attributes, so that repository keeps the merge conflicts
that this design removes.

## 4. The store: an append-only event log, and a one-way boundary

**The event log is the truth. Every other file is derived.** Each change is a new line, and
the state of a record is a fold over its events. Two writers append different lines, so
conflicts are rare. The history is in the data, so the audit trail does not depend on git
history after a squash, a rebase or a shallow clone.

The rejected alternative is a snapshot with one line per record. Such a file rewrites the
whole line of a record on each change. It is not append-only, two edits to one record
conflict, and the file cannot tell how a state came to be. So the log is authoritative, and
each snapshot or index is derived. You delete a corrupt derived file; you do not repair it.

The cost of a fold grows with the number of events. A naive reader folds again for each
query. §4.6 answers the common query without an index.

**The derived snapshot is gitignored, never committed.** A committed derived file makes two
sources of truth: two branches each rebuild it, and git cannot union-merge a record that
changed on both sides. That breaks requirement 1 in §4.3.

- A reader rebuilds the snapshot when it finds the snapshot stale.
- The first line of the snapshot is a header. It carries the id of the last folded event,
  the event count, the log line count and the snapshot format version, which is 2.
- A snapshot is stale when its line count, last event or format version differs from the
  log. So a crash between an append and a rename cannot serve old state.
- A reader refuses a snapshot whose format version is newer than its own, and folds the log
  instead.

**Rotation is by period. The kit archives old log files and never prunes them**, because
requirement 6 in §4.3 folds the whole history. A rebuild reads every `events-*.jsonl` file
by contract. Rotation alone does not make a fold cheaper, because the fold parses the same
events in any number of files. So each rotation writes a derived checkpoint snapshot. A
normal fold then reads the latest checkpoint plus the newer logs, and the full fold stays
available.

**The dependency direction is one-way: the engine imports the kit, and the kit imports
nothing.** The kit does not read the engine's configuration, logging, session state or
policy. It reads its own committed data and takes everything else as arguments. Redaction is
also an argument: each entry point accepts a redactor and imports none. The kit uses only the standard
library, with no third-party package, no network and no subprocess. It uses no syntax newer
than Python 3.9, because a consumer's Python can be older.

The `kit-boundary` commit hook enforces this direction. It ships with the kit and also runs in
the authoring repository's full verify run. An import linter cannot enforce it. The kit is
flat modules with no `__init__.py` and outside any package, so the linter never opens a kit
file and always passes.

The kit is a requirement for three reasons:

1. It makes "no external binary in the critical path" a test instead of a claim.
2. A kit can be built and tested alone and changed behind one seam.
3. **The data outlives the tool.** A work ledger is the longest-lived artifact of a harness.
   If the harness is abandoned, the ledger and its scripts must stay usable.

### 4.0 Sharding — a writer appends to its own file

**`merge=union` does not stop a forge from flagging a pull request as conflicting.** GitHub
computes mergeability before the merge and ignores `.gitattributes`, and its auto-merge
refuses a flagged pull request (GitHub community discussion 9288).

A test on GitHub used two arms with the same `.gitattributes`. Each arm advanced its base by
one append and then opened a pull request for a second append:

| arm | the pull request changes | `git merge` locally | GitHub `mergeable` |
| --- | --- | --- | --- |
| one shared log | `events-0001.jsonl` | MERGEABLE | **CONFLICTING**, state DIRTY |
| one file per writer | `pending-<writer>.jsonl` | MERGEABLE | **MERGEABLE**, state CLEAN |

The same commits merge cleanly in a local git and are refused by the forge. So a local merge
that succeeds proves nothing about the pull request. A shared log is a conflict surface on a
forge, whatever the attributes say.

**A writer appends to `pending-<writer>.jsonl`, never to the trunk log.** Two branches then
change two different paths, and the forge has nothing to flag.

- The kit derives the writer name from `.git/HEAD` by a file read, not a subprocess.
- In a linked worktree, the kit follows the `.git` file to that worktree's own `HEAD`, so
  each lane is its own writer.
- A directory outside a repository keeps the single trunk log, so an existing ledger reads
  and writes as before.
- `events.append` accepts `writer=` for a caller that knows the writer better.

**A shard separates branches, not clones.** Two checkouts on the same branch write the same
shard path, and their appends meet in one file. The union merge driver handles that case, so
the install declares the attribute on the shard glob as well as the trunk glob. A shard
removes the conflict between branches, and the attribute removes the conflict within a
branch.

**This is the one place where the kit reads a file that it does not own.** Git is already
the substrate of the design. The alternative, a required `--writer` on each call, would make
the standalone install worse than the bundled one.

**A shard is temporary. `compact` folds it into the trunk log and deletes it.** The number of
files must stay bounded by the number of open writers, not by all writers that ever existed.
One `git add` over a directory of shards costs:

| shards | NTFS | ext4 |
| --- | --- | --- |
| 1,000 | 2.89 s | 0.16 s |
| 10,000 | 35.59 s | 0.66 s |
| 100,000 | 374.27 s | 3.48 s |

At about 8 lanes a day, shards that are never compacted pass 3,000 files in a year. So `fsck`
warns above 1,000 uncompacted shards and refuses above 10,000. `shards` lists the pending
shards.

Compaction needs no central serializer, so it is a kit command. Two clones that compact the
same shards and push converge. The union merge concatenates, and a duplicate event folds
once because event ids are content-derived. Git resolves a shard deleted on both sides. An engine calls
the same command where it commits tracker state; it is a caller, not a second mechanism.

**The benefit depends on who commits the ledger.** When a developer commits the ledger on a
feature branch, sharding keeps the pull request mergeable. A harness that commits tracker
state from one base checkout has one committer and no branch conflict. There, sharding gives
only a bounded file count.

**Rotation refuses while a shard holds uncompacted events.** A checkpoint records the line
count of the logs that it covers, and `fold_resumed` resumes only when that count matches. A
rotation during an open shard writes a checkpoint that no resumed fold can match, and the
fold silently falls back to the whole history. Shards also use their own
`pending-*` namespace. `period_of` reads all text after `events-` as a period, so a writer
name there would corrupt both `period_of` and `rotate`.

### 4.1 Ordering — the per-item sequence

Each event carries a **per-item integer sequence number**. The writer reads the item's
current maximum and writes the maximum plus one, and the event id breaks a tie. The fold
**sorts into this order before it folds**, so the fold is a deterministic function of the
event set.

Deduplication by event id handles the duplicates of a union merge, but not the order. Status
is ordered: `open → in_progress → done` and a reopen from `done` give different states in a
different order. A union merge puts conflicting hunks in any order. A fold that commutes over
raw events would be a conflict-free replicated data type, which costs far more than this
problem needs. One integer field and one sort rule give the needed order at the lowest cost.

**A timestamp is never the sort key** (§9.5). One skewed clock would reopen a `done` item.

Two branches that increment the sequence of one item at the same time make a **visible fork
that `fsck` reports**. A visible conflict is better than a silent wrong order. A fork is a
warning when its events set nothing in common, such as two comments. It is broken, as
`conflicting-fork`, when two of its events set one status or one field to different values
and no later event sets that key again. `resolve` appends that later event with the current
value, so the tie becomes a decision.

### 4.2 Secrets, size, and the committed-ledger trust boundary

Agents paste command output, so a token, an environment fragment or an absolute path will be
written some day. The design makes such a leak permanent. The log is append-only, a delete is
a tombstone, archives are never pruned, and true removal needs a history rewrite.

A repository that forbids committed machine paths has a second risk. A path in one event
trips that repository's own scanner, and the tracker can no longer commit its state.

Two controls run inside the validation of each write:

- **Redaction.** Each write passes its values through the redactor that the caller supplies,
  for secret patterns and absolute paths. The kit's command line runs no redactor unless its
  caller passes one to `main`.
- **A per-event size cap.** Each free-text value is cut at 4,096 bytes
  (`events.MAX_TEXT_BYTES`). The event records `<key>_truncated` and
  `<key>_original_length_bytes`, so the cut is visible (§9.1). On a kind with no declared
  bound, a value above the cap is refused, not stored unbounded. The cap also bounds
  interleaving (§4.4).

Comments are the largest share of tracker traffic (45% in one measured ledger), so agent
verbosity drives growth, and the cap is its only bound. `events.py` holds and tests the
cap's exact rules.

`events.withdraw` removes the free text of one event from the log. It rewrites that line
under the ledger lock and appends a `withdrawn` event that names the new line and the reason.
Git history still holds the old line.

### 4.3 The ten requirements, and the weakest link in each

| # | Requirement | Weakest link |
| --- | --- | --- |
| 1 | Single source of truth for where implementation stands | Fails if the snapshot is ever committed (§4) |
| 2 | Resume at the correct place in a new session | The claim race — see §4.5 |
| 3 | A team can organise work with it | Ordering across machines; needs §4.1's sequence |
| 4 | Work is transparent | Committed plain text, diffable in review |
| 5 | Reconstruct work history for analysis | Needs `field` events, not only status |
| 6 | Greenfield reimplementation from history | **Restated** — see below |
| 7 | Recover when defective | Rebuild; repairs only by appending |
| 8 | Partial archival at size | Needs the rotation checkpoint, not rotation alone |
| 9 | Work reports | Fold over events |
| 10 | Visualisation | **Restated** — on-demand, not real-time |

**Requirement 6 means the specification, the order of work and the reasons, not the
software.** A ledger can rebuild what was decided, in what order and why. With the commit
recorded for each landed item, it can point at what was built. A literal reimplementation
would need each interface decision in events, and no write-time gate can verify that. So
**decisions and acceptance criteria must be first-class events with their reasons**, not
prose in a description field.

**Requirement 10 means regeneration on demand.** A generated graph or a static board, such
as the page that `board` writes, is not real-time.

The `actor` of requirement 5 tells under which identity a write was made. It is an opaque
lease holder, such as a lane, a session or an agent, never a person as assignee (§4.5). The
kit's command line sets it from the environment: `agent:<name>` from `BR_AGENT_NAME` or
`AI_AGENT`, `agent:claude-code` when `CLAUDECODE` is `1`, and `operator` otherwise.

### 4.4 Concurrency and resilience

One lock serializes the writers of a ledger. Events are appended as plain lines. A snapshot
is published by a write to a temporary file and an atomic rename. Contention is reported as
**retryable**, so a caller waits and tries again instead of failing a gate.

- **Torn line.** Before an append, the writer checks that the last byte is a newline, and
  writes one if not. Otherwise the next append joins a partial line and corrupts a good
  event. The fold skips one unparseable last line with no final newline, silently. `fsck`
  quarantines any other unparseable line by line number, and nothing edits it.
- **The lock is the guarantee, not `O_APPEND`.** POSIX makes each `write()` call atomic on a
  regular file, but a buffered writer can split one long line into several calls, and
  `O_APPEND` is not atomic on NFS. The size cap of §4.2 limits the exposure; it does not
  replace the lock.
- **No `fsync` for each event.** The push is the durability boundary. An `fsync` would
  destroy the short lock hold that makes one writer at a time practical.
- **An orphaned lock must not block every lane.** The lock file holds a process id and a
  monotonic clock reading. A writer steals the lock in three cases: the process is dead,
  the reading is from another monotonic epoch, or the hold is older than 30 seconds. The lock uses `O_CREAT|O_EXCL` and this steal rule, because `fcntl.flock`
  does not exist on Windows (§12).
- **A writer that rewrites a whole log takes the same lock as an append.** A rewrite reads
  the file, writes a temporary file and renames it. Without the lock, it silently deletes an
  append made in between, and the log still parses.
- **Encoding, line endings and merging.** Declare `events-*.jsonl -text merge=union` and
  `pending-*.jsonl -text merge=union` in `.gitattributes`. Without `-text`, a Windows
  `autocrlf` checkout rewrites the ledger. Without `merge=union`, two branches that each
  append an event conflict. Pass `encoding="utf-8"` to each `open()`, because the default is
  locale-dependent and corrupts a non-ASCII comment on a cp1252 host.
- **Repairs only append corrective events.** `fsck` never edits a line; otherwise the log
  stops being the truth.

### 4.5 Claiming, and forward compatibility

With concurrent lanes, the read of the ready set and the write of the claim must be **one
locked read-check-write, not two calls**, or two lanes take the same item. The kit's
`update` reads the record and appends under one held ledger lock. It does not check
readiness again, so a caller that dispatches concurrent lanes owns that check. Each event
carries an opaque `actor` string, and a lane claim is a **lease**, not an assignment.

Forward compatibility must be tolerant in the correct direction:

- The fold **skips unknown event kinds and unknown fields, and preserves them verbatim** on
  any rewrite.
- `fsck` **warns** on an unknown kind and never fails on it. Otherwise an old reader reports
  false corruption in a newer ledger.
- The ledger carries no format version event. The snapshot header carries a format version
  (§4), and a reader refuses a snapshot newer than its own.
- No rule catches a new kind that replaces the meaning of an old one: old readers become
  silently wrong. So **never change the meaning of a kind, never reuse a kind name, and only
  add kinds and optional fields.**

**A write names only fields from the field table.** `fields.py` gives each record field a
role and the reader that uses it; `fields` prints the table. A write refuses an unknown field
name, an import-history field that only `import` writes, and a derived field such as `dates`.
A section that the ledger's `template.json` declares is also writable.

The line format is **one JSON object for each event, one event on each line**. It is safe,
extensible and the format of the harness's other ledgers. A derived edge list and a derived
record snapshot are projections of it.

Parse speed does not decide the format. At 603 records and about 2 MB, a full read and parse
costs 5.8 to 7.6 ms. A full serialize, rewrite and rename costs 5.5 to 5.8 ms. But the
whole ledger is about half a million tokens, so no file format helps an agent that reads all
of it. A **scoped view** helps: one record, its edges and its open blockers. That is a
command, not a format.

**Cross-repository shape.** Each repository owns its ledger under its own prefix and is its
only writer. Work across repositories moves as offers that each participant records in its
own ledger. So no component writes across a repository boundary, and no shared artifact
needs coordination.

### 4.6 The running aggregate — the tail answers the common query, the fold stays the authority

**Each event carries the item's running aggregates as they are immediately after that
event.** This field is `totals`: the event count, the attempt count, the spend
(`spend_micros`) and the last status. The common query (the spend, the attempts and the event
count of an item) then reads the item's last event and folds nothing.

Four rules keep this cache from becoming a second source of truth:

- **The fold is the authority, and a carried total is a cache in the log.** A reader that
  must be correct folds. `fsck` (§13) folds again and reports each event whose totals
  disagree. A disagreement is a **finding, never a repair in place** (§4.4).
- **One accumulator, called from both sides.** The writer computes the totals with the
  fold's own accumulator over the previous totals and the new event. Two copies of the rule
  would drift.
- **Only pure functions of the events, and only for each item.** A carried value depends
  only on the events up to and including its own, such as counts, sums and the last status. It never
  reads a clock (§9.5) or anything outside the log. The writer already reads the item's
  maximum sequence (§4.1), so the previous totals come with that read. A ledger-wide counter
  would put every item behind one number and fork on every branch.
- **The totals are correct only while the item's sequence chain has no fork.** Two branches
  that append to one item compute from the same predecessor. After a union merge, the last
  event omits the other side. This is the fork that §4.1 already reports. The carried totals
  of a forked item are **void until a fold restates them**.

**The cost of the tail read.** The whole-ledger totals are the last line of the current file.
The totals of one item come from a reverse scan that stops at the item's first hit. Each
rotation checkpoint (§4) carries the totals of every item, so the worst case is the current
file plus one checkpoint, never the whole history. This is a **requirement on the
checkpoint**. An index is justified only when a query across items cannot be served this way.

**The totals are also evidence.** The total is recorded at the moment of the write. So the
spend that an item showed when a dispatch marker was written is available without a fold. A
snapshot of the present cannot give that.

## 5. Import and coexistence with a tracker being replaced

A cutover is never done in one step, because the tracked work continues. The kit ships the
three mechanisms that make the cutover incremental. The rules below are their contract.

**Import** reads another tracker's JSONL export with `import`.

- Each imported event carries provenance `EXTRACTED` (§9.6) and the source name
  (`imported_from`). Each created record also carries the export's digest (`import_digest`).
- **The import can run again.** A record that the ledger already holds is not created again.
  The report names a record whose fields differ as `diverged`, and a record from the same
  source that the export no longer holds as `absent`. It overwrites neither.
- `--dry-run` reports the same plan and writes nothing.
- **The order is fixed.** Import while the other tracker is still authoritative, then
  declare the residual baseline, then start the dual write. An import after the dual write
  starts makes the owned side follow the other one instead of being compared with it.
- **The kit's own entry point covers the records and their edges.** It creates, reads,
  queries, updates, closes, links and tombstones records, with no engine import and with
  redaction as an argument.

**Shadow mode** reads the same ledger, answers the same queries read-only, and asserts the
same verdicts for phase derivation, the ready set and gate status. Four rules apply:

- **It proves that the dual write agrees, not that history agrees.** The run judges records
  created after the cutover. The earlier difference is *declared*, not compared.
- A record that the **reference** holds and the ledger does not has no event to classify. So
  the declaration captures that set once, at the cutover, in a committed baseline file. **A
  second declaration is refused**, because it would absorb a real failure into history.
- **An empty set of records in scope is inconclusive, never clean.** Until records exist
  after the cutover, the run does not permit the flip. `clean` and `conclusive` are two
  separate answers.
- A **refused reference voids the run**, whatever the scope. The boundary decides which
  records are judged, never whether the reference was the live tracker.

**Dual write** runs for one release with the other tracker still authoritative. A write
surface with no translator **raises** instead of logging, so the work stops instead of
silently diverging. A guard placed after the write cannot refuse it, so the order is:
decide, then spawn, then mirror.

**Flip** the source of truth when the differential is clean and conclusive and no surface
without a translator is in use.

### 5.1 Three risks in the import step

An export that its owner calls "not the canonical cross-machine sync channel" has three
consequences for an importer. None is fatal.

- **The export format will drift.** Pin the import against a known good export and expect
  format changes.
- **Import is upsert-only.** An export "cannot infer that records absent from an export were
  deleted, pruned, or simply never exported". So an export cannot express a deletion, and the
  importer treats tombstones as a first-class concern. Absence is ambiguous by construction
  in an upsert-only format, which is a different problem from an unknown event kind (§13).
- **A one-shot import is the only import.** The import cannot carry deletions, so the
  differential compares against the **live** tracker, never against a second import of its
  export. Two copies derived from one lossy export agree with each other and prove nothing.

## 9.1 Compaction — declined

**No lossy compaction.** Git's delta and zlib compression already compress a ledger of
similar JSON lines well, and without loss. Compaction discards evidence, and evidence is the
purpose of the store.

Four things bound growth instead:

- git compression;
- a rollup at the point where work ships, where the harness above the store keeps one;
- the event log itself, which makes each write as large as the change, not as the record;
- **honest truncation**.

None of the first three bounds one pasted payload: a 5 MB log in one event goes into every
clone. The per-event cap of §4.2 makes that limit explicit. The recorded original length
keeps the cap from being lossy compaction. Compaction hides that it discarded evidence.
Truncation **says on the record that it cut, and by how much**.

Watch the **maximum line length**, not the total size, as the early warning.

## 9.2 Ranking — a pure function of the graph

The ranking is a pure function of the graph. It keeps only ready items, then orders them by
priority, then by the descending count of live blocking dependents, then by id. It **ignores
creation time**, because an order by age makes the dispatch order depend on the clock for an
unchanged graph.

- The dependent count uses only **blocking edges from live dependents**. A `related`
  dependent never waited, and a closed dependent is finished work.
- The score packs both terms into one integer, capped at 999 dependents, and `explain()`
  decodes it. So a **recorded** score stays readable without the graph.
- `ready` **holds back a record labelled `refine`**, so a record that waits for refinement
  is never dispatched. `refine` lists the open records that a refinement pass owes: each one
  labelled `refine`, or refused by the definition of ready.

**The absence of age is structural.** The input type of the ranking carries no timestamp,
although the ledger has timestamps. So nobody can break the rule by accident.

A recorded rank is also evidence. A dispatch marker carries the score, the rank, the
fallback rank and the **policy version**, because a score without its policy version cannot
be read. The ranker recommends only unclaimed work, so a null rank must stay different from
an unrecorded rank.

## 9.4 Identity — opaque record ids, content-derived evidence ids

- **Records change.** Titles, descriptions and criteria are edited often, so an id derived
  from content would drift or lie. A record id is **opaque and stable**: a prefix, a short
  random root, and a dotted child suffix that counts up (`<prefix>-<root>.<n>`). It sorts
  naturally. An id is never reused, and a delete leaves a tombstone.
- **The id length comes from a stated collision budget** (§9.4.1), and it grows with the
  ledger. Only new ids get longer, because an existing id never changes.
- **Evidence does not change.** A decision, a found fact or a dispatch marker records one
  moment. So its id **is** derived from content, and a second recording of the same evidence
  changes nothing.
- **No slugs in ids.** A slug adds hyphens that read as a prefix boundary, and that breaks a
  commit-message gate that parses the prefix.

### 9.4.1 The declared collision budget, derived

A mint can check only the ids that its own writer can see. Two branches that mint from the
same base can collide without a sign, and merge into one id. So the root length comes from
the birthday bound against a declared maximum probability:

```text
P(collision) ≈ 1 - e^(-n² / 2N),   N = RADIX ** length
```

Here *n* is the number of **distinct roots** under one prefix, not the number of records,
because children share their root. The declared target is `MAX_COLLISION_PROBABILITY` =
`1e-4`: one chance in ten thousand that any two roots ever minted collide. The target gives:

| root length | id space N | max roots at P ≤ 1e-4 |
| --- | --- | --- |
| 4 | 1,679,616 | 18 |
| 5 | 60,466,176 | 109 |
| 6 | 2,176,782,336 | 659 |
| 7 | 78,364,164,096 | 3,958 |

The table is derived. `max_population` computes each row, and a test parses this section and
asserts that the two agree. The exact birthday probability, `1 - Π(1 - i/N)`, is lower than
the approximation on each row, so the approximation is the conservative side. The test also
asserts this.

The target is `1e-4` and not tighter for two reasons. A collision loses no data: the local
check tries again, and a collision across branches is a visible fork, not a silent
overwrite. And people read and type ids, so each extra character has a cost.

**Adaptive length is safe because an existing id never changes.** Only a new root gets
longer, and each issued id keeps its length. `mint_root_id` treats every issued id as taken
forever. The caller passes every id ever minted, including the ids of deleted records, and
the mint discards a candidate that matches any of them.

## 9.5 Time — a timestamp is evidence, never a constraint

The order comes from the log, not from the clock. The fold reads events in sequence order
(§4.1) and nothing else. Two events with equal or reversed timestamps are normal, not a
conflict.

- **A write is never refused because of timestamp order.** A check that
  `updated_at >= created_at` fails when the clock steps back between two writes, and an NTP resync does
  that often. Record what the clock said and continue.
- **No order, rank, staleness check, deduplication or idempotence depends on a timestamp.**
  Ranking ignores creation time (§9.2), and the other rules key on sequence and content
  (§9.4).
- **The derived dates only display recorded times.** The fold computes `dates` for each
  record: `created` is the first event time, `updated` the last event time, and `closed` the
  time of the closing status. An imported record uses the times that its export asserts.
  `show` and the snapshot carry these dates, and nothing orders or refuses by them.
- **Durations use a monotonic clock.** The store times itself with a monotonic counter. It
  only records the wall clock.

**Measured evidence.** One production append-only journal has no sequence numbers and mints
event ids from the wall clock plus a random part. In its published fixture of 6,467 events,
**44.5% of events share a millisecond** with another event.

- At that rate, a millisecond timestamp gives no order for nearly half the log. A sort by it
  gives an arbitrary order inside each group.
- The only real order is the file position. A union merge, a rebuild or any sort destroys it
  silently, and nothing in the data shows the loss.
- A harness writes in bursts: one pass appends for several lanes in the same few
  milliseconds. That is exactly the pattern that makes collisions.

The general rule: **we assign the total order of the ledger, so a bad host clock reduces the
quality of the evidence and never the correctness of the state.**

## 9.6 Provenance — every edge says how it got there

Without provenance, three kinds of edge look the same in the graph. A human asserts one. An
agent proposes one from overlapping scope globs. A merge queue infers one after a conflict. Only the first can gate a landing without review.

| Label | Meaning | Disposition |
| --- | --- | --- |
| `EXTRACTED` | explicitly asserted by a human, or mechanically derived from a fact in the repository (an import, a shared file in two scope globs) | trusted; may gate a landing |
| `INFERRED` | proposed by an agent, or deduced from a second-order signal (a bounce, a co-occurrence) | usable, but visible as a proposal |
| `AMBIGUOUS` | the derivation is uncertain | **routes a decision item**; never silently gates anything |

Provenance is part of the schema, not a convention, for three reasons:

- Evidence must be attributable. An edge is evidence about the shape of the work, and it
  otherwise carries no attribution.
- `AMBIGUOUS` uses a path that already exists: an uncertain machine judgment goes to the
  decision queue.
- A coupling edge added after one observation is an inference. Recorded as `INFERRED`, it
  does not pass for a declared dependency, and the ledger can tell how often inferred
  couplings are correct.

## 12. Portability

- **No absolute paths, in any field**, provenance included. A path is specific to one
  machine, and the ledger is shared.
- **LF and UTF-8, explicitly.** Mark the ledger in `.gitattributes`, not by `text=auto`.
  Write newlines and UTF-8 without platform defaults. Read tolerantly: a stray carriage
  return must not corrupt a fold.
- **No POSIX-only locking.** The lock must work on Windows, so no bare `fcntl`. The
  temporary write and atomic rename is portable and is the intended mechanism (§4.4).
- **No new runtime dependency.** A pure-Python store works on each platform that the host
  already tests (§4).
- **Nothing machine-specific in any file that the kit writes or installs.** A tracked file
  with an interpreter path or a repository path leaks a user name into a commit and breaks
  each teammate's checkout.
  - A committed file uses a placeholder that the host substitutes, and a launcher that each
    committer has. It never uses a bare `python3`, which on Windows can open a store page
    through an execution alias.
  - **When neither a portable nor a machine-local form is possible, refuse.** A fallback to
    the absolute path brings the defect back.
  - A kit test fixture must be a repository that contains the kit, or the test proves
    nothing.

## 13. Failure modes and recovery

An append-only log fails differently from a database, and these differences are the benefit
of the design:

| Failure | Recovery |
| --- | --- |
| Torn write (crash mid-append) | The fold skips the partial last line; the events before it are intact |
| Unparseable interior line | Quarantined by line number and reported; never edited |
| Corrupt derived snapshot or index | Delete and rebuild from the log; never repaired in place |
| Bad merge (both sides appended) | Both event sets survive; the fold is order-independent for distinct events |
| Bad merge (same record edited) | Two events, both kept; the resolution is a *later event*, not a lost one |
| Unknown event kind (newer writer) | Preserved verbatim and skipped by the fold, with a warning |

Two commands are requirements:

- **`fsck`** folds the whole log and reports each line that is unparseable, unknown or
  referentially broken.
- **`fsck --rebuild`** regenerates each derived file from the log alone, then checks.

Without them, nobody can check that the log is the truth. They belong together: a rebuild
with no check that the derived file matches the log is a guess.

## 14. Testability

The properties to assert, in addition to the differential of §5:

- **Fold determinism.** Two folds of the same log give byte-identical derived files.
- **Order independence.** A fold of a shuffled log of distinct events gives the same state,
  so concurrent appends are safe.
- **Idempotent replay.** A second append of an event with an existing id changes nothing.
- **Round trip.** Each field survives a read, change and write, including a field that the
  current version does not know.
- **Property-based generation** over event sequences, because the interesting defects are in
  interleavings that a hand-written case does not find.

## 15. Non-goals

This kit is not a general-purpose issue tracker. It has no user authentication or
authorization, no sync server or hosted service, and no web application. It has no sprint,
estimate or reporting ceremony beyond what a loop uses. It has no maintained terminal
interface, no real-time collaboration, and no import from other trackers beyond §5. Each of
these makes a tool like this one hard to maintain, and the loop needs none of them.

**No LLM monitoring of the ledger.** This rejection is the plausible one, so it has reasons:

- It puts a paid third-party service in the runtime path of the store. Model ids, prices
  and availability change on another party's schedule.
- It breaks the kit boundary, which never calls the network or a model (§4).
- It is not deterministic. A monitor that can give two verdicts on the same log cannot feed a
  gate.

A stall watchdog on a monotonic clock already detects a lane that stops making progress, as
§9.5 requires.
