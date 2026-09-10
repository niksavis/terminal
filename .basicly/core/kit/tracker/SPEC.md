# The tracker kit's specification

What this store guarantees, for a reader who has **only the kit**. The engine's own
tracker rules live in that repository's architecture document; nothing here depends on
reading it, because a consumer who installs the kit never receives it.

## How to read the section numbers

They are **inherited, not designed**. This kit's modules cite their requirements as bare
section marks, and the authoring repository gates every one of them against a heading
defined below, so the numbering of the requirements document this file replaces is kept
exactly as it stood rather than renumbered under its own pointers. The gaps are real: a
number absent here was engine-side, or was decision narrative that ended with that
document.

Two rules govern what is written here, and the second is why this file is short:

- A rule the kit **implements** is stated as a rule, with the reason the code cannot
  carry — which measurement fixed a threshold, which defect a guard exists for.
- A claim that merely **restated shipped code** was dropped rather than relocated. The
  code is the authority; this file is the contract it is held to.

## 4. The store: an append-only event log, and a one-way boundary

**The event log is the truth; every other file is derived.** Every change is a new
line, and a record's state is a fold over its events. Conflicts are rare by
construction because two writers append different lines, and history is *in the data*,
so an audit trail does not depend on git history surviving a squash, a rebase or a
shallow clone.

The alternative it rejects, stated because it is the one a reader proposes: a
line-per-record snapshot rewrites a record's whole line on every change. It is not
append-only, two edits to one record conflict, and the file alone cannot answer *how
did this get here*. So the log is authoritative and both the record snapshot and any
index are derived and disposable — a corrupt derivative is something you delete, not
something you repair.

The cost is honest: a fold is O(events) and a naive reader re-folds per query. §4.6 is
the one field that answers the common query without an index at all.

**The derived snapshot is gitignored, never committed.** Calling a file derived and then
committing it recreates the dual-store failure this design exists to escape: two
branches each rebuild it, any record changed on both sides is a same-line conflict git
cannot union-merge, and until someone rebuilds, the repository holds two sources of truth
that disagree — which kills requirement 1 in §4.3. It is regenerated on a stale read and
by a checkout hook. **Its first line carries the id and count of the last folded event**,
so any reader can detect staleness against the log; without that, a crash between append
and rename serves stale state forever with nothing to notice it.

**Rotation is by period, archived and never pruned**, because §4.3's requirement 6 folds
the whole history. A rebuild therefore globs `events-*.jsonl` **by contract, not by
convention**. Rotation alone does not reduce steady-state fold cost — the same events are
parsed however many files hold them — so the scaling answer is a derived **checkpoint
snapshot at each rotation boundary**: steady state becomes checkpoint plus current file,
while the full-history fold stays available.

**The dependency direction is one-way: the engine imports the kit; the kit imports
nothing.** The kit may not read the engine's config loader, its logging, its session
state or its policy module. It reads its own committed data and takes everything else as
arguments — including redaction, which is why the entry points accept a redactor rather
than importing one. Standard library only, no third party, no network, no subprocess, and
no interpreter syntax newer than 3.9, because a consumer's Python is older than the
authoring repository's floor.

That direction is **gated, not intended**: `kit-boundary` is a commit hook that ships
with the kit and a check in the authoring repository's full verify run. It replaced a
claim that an import linter already enforced it — which was *unenforceable, not merely
unimplemented*: an import linter analyses one root package, and the kit is flat modules
with no `__init__.py`, outside that package and not on `sys.path`, so the tool never
opened a kit file and would have reported success forever. A fail-open gate is
indistinguishable from a pass.

Three reasons the kit is a requirement rather than a nicety:

1. It turns "no external binary in the critical path" into a test instead of a claim.
2. It de-risked the migration: a kit can be built and tested standalone and swapped
   behind one seam, rather than as N simultaneous parser rewrites.
3. **The data outlives the tool.** A work ledger is the longest-lived artifact a harness
   owns. If the harness is abandoned, the ledger and its scripts must stay usable — a
   property no in-package-only design has.

### 4.1 Ordering — the per-item sequence

Every event carries a **per-item integer sequence number**. The writer reads the item's
current max and writes max+1; ties break by event id. The fold **sorts into that
canonical order before folding**, which is what makes "the fold is a deterministic
function of the event *set*" true rather than aspirational.

This is necessary and it is not a CRDT. Idempotency by event id handles union-merge
**duplication** and does nothing about **ordering** — and status is inherently ordered:
`open → in_progress → done` and a `done → open` reopen fold to different states depending
on sequence. A union merge concatenates conflicting hunks in arbitrary side-order and
guarantees neither ordering nor dedup, so a genuinely commutative fold over raw events
*would* be a CRDT, which §15 rejects. One integer field and one sort rule is a degenerate
Lamport clock without the subsystem, and it is the whole cost.

**A timestamp may not be the sort key** (§9.5). One skewed clock would resurrect a `done`
item.

Two branches incrementing one item's sequence concurrently produce a **visible,
fsck-reportable fork**, which is strictly better than silent misordering: a conflict you
can see beats a state you cannot explain.

### 4.2 Secrets, size, and the committed-ledger trust boundary

Agents paste command output, so a token, an environment fragment or an absolute path
**will** eventually be written. Every property that makes this design good makes a leak
permanent: append-only, delete is a tombstone, archives are never pruned, and true
removal means a history rewrite that needs explicit confirmation.

Nearer and more concrete: a repository that forbids committed machine-specific paths will
have a path in a gate event trip its own scanner and **wedge tracker writes entirely** —
the tracker becomes unable to commit its own state.

The control is prevention inside the validation that already runs on every write: a
**redaction pass** (secret patterns, absolute paths rewritten repository-relative) and a
**per-event size cap**. The cap does double duty — §4.4 needs it as the interleave bound.
Comments were 45% of tracker traffic when this was measured, so agent verbosity is the
growth driver and the cap is the only thing bounding it.

What survives here is that **trust-boundary framing**, because it is the argument for the
cap rather than the cap's contract: a leak into an append-only committed log is
permanent, and the cap is the only bound on a single pasted payload. The cap's own rules
are built and asserted in `events.py`, which is where a reader should check them.

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

**Requirement 6 is spec, sequencing and rationale reconstruction — not the software.** A
ledger can faithfully rebuild *what was decided, in what order, and why*, and with the
commit sha recorded per landed item it can point at what was built. Literal
reimplementation would need every interface decision articulated in events, which no
write-time gate can verify. To make even the honest version real, **decisions and
acceptance criteria must be first-class events carrying their reasoning**, not prose
buried in a description field.

**Requirement 10 is on-demand regeneration.** A generated graph and a static board
rebuilt on write is not real-time, and calling it that would be an overclaim one notch
smaller.

Item 5's `actor` is the field a caller uses to say who a write was made under. It is an
opaque lease holder — a lane, a session, an agent — and never assignee-as-person
modelling (§4.5).

### 4.4 Concurrency and resilience

Single writer per ledger, one lock, snapshot published write-temp-then-atomic-rename,
events by plain append, writes only from the base checkout. Contention is reported as
**retryable** so callers back off rather than failing a gate.

- **Torn line.** Before appending, check the last byte is a newline and write one first if
  not, or the next append concatenates onto a partial line and corrupts a **good** event.
  The fold tolerates exactly one unparseable *trailing* line silently; interior garbage is
  an fsck finding, quarantined by line number and **never edited**.
- **`O_APPEND` is not the guarantee — the lock is.** POSIX makes the offset update atomic
  per `write()` on a regular file, but a buffered writer flushes in ~8 KiB chunks, so one
  logical line larger than that becomes several syscalls a concurrent appender can
  interleave between; and `O_APPEND` is not atomic on NFS at all. §4.2's size cap bounds
  the exposure; it mitigates interleaving and is not the concurrency guarantee.
- **No `fsync` per event.** The push is the durability boundary. Stated explicitly so
  nobody later adds one and destroys the millisecond-scale lock hold that makes
  single-writer viable.
- **An orphaned lock must not wedge every lane.** The lock file carries a pid and a
  monotonic reading and is stolen when the pid is known dead, when the reading is from
  another monotonic epoch, or when the hold outlives its stale bound. `O_CREAT|O_EXCL`
  plus that steal rule, because **`fcntl.flock` does not exist on Windows** and §12
  commits to three platforms.
- **A writer that rewrites a whole log takes the same lock an append takes.** The rule is
  stated because the exception was found: an operation that rewrote a log rather than
  extending it — reading the file, writing a temp file, renaming — destroyed a concurrent
  append *silently*. The rename succeeded, the log parsed, and the fold stayed consistent,
  because the lost line was never in the text that was re-emitted.
- **Encoding, line endings and merging.** Declare `events-*.jsonl -text merge=union` in
  `.gitattributes`: without `-text` a Windows `autocrlf` checkout rewrites the ledger in
  place, and without `merge=union` two branches that each append an event conflict instead
  of concatenating (basicly-aabirfj). Pass `encoding="utf-8"` to
  **every** `open()` — the interpreter default is still locale-dependent, so an unmarked
  open on a cp1252 host corrupts on the first non-ASCII comment.
- **`fsck` repairs only by appending corrective events**, never by editing lines, or it
  quietly becomes an editor and the log stops being the truth.

### 4.5 Claiming, and forward compatibility

With concurrent lanes, reading the ready set and writing the claim must be **one locked
read-check-write inside the kit, not two calls**, or two lanes take the same item. Every
event carries an opaque `actor` string; a lane claim is a **lease**, not an assignment.

Forward compatibility has to be tolerant in the right direction:

- The fold **skips unknown event kinds and unknown fields, preserving them verbatim** on
  any rewrite.
- `fsck` **warns** on unknown rather than erroring, or an old reader hitting a newer
  ledger reports false corruption. A warning is printed and never fatal.
- One `format_version` event. A reader below it **still reads but refuses to write**.
- The limit no rule fixes: a new kind that semantically supersedes an old one makes old
  readers silently wrong. The discipline is therefore **never change a kind's meaning,
  never reuse a kind name, only add kinds and optional fields.**

The line shape is **JSON objects, one event per line** — safe, extensible, and the shape
the harness's other ledgers already use. A derived edge list and a derived record
snapshot are projections of it, which costs nothing architecturally because derivatives
are already mandated disposable.

The measurement that governs the choice, and the reason not to re-litigate it on parse
speed: at 603 records and roughly 2 MB, a full open-read-parse cost 5.8–7.6 ms and a full
serialize-rewrite-rename 5.5–5.8 ms. The machine does not care which line format is
picked at this scale. What matters instead is that reading the whole ledger is on the
order of half a million tokens, so no on-disk format saves an agent that reads all of it:
the dominant variable is whether a **scoped view** exists — one record plus its edges plus
its open blockers — which is a command rather than a format.

**Cross-repo shape:** each repository owns its ledger under its own prefix and is its only
writer. Cross-repo work moves as offers recorded by each participant in its *own* ledger,
so no component ever writes across a repository boundary and there is no shared artifact
to coordinate on.

### 4.6 The running aggregate — the tail answers the common query, the fold stays the authority

**Every event carries the value of the item's running aggregates as they hold immediately
after that event.** One field — `totals` — and the overwhelmingly common query (*what is
this item's spend, how many attempts has it had, how many events does it carry*) is
answered by reading the item's last event instead of folding its history. It costs one
field per line.

Four rules, and the first is what keeps a denormalized total from recreating the
dual-store defect §4 exists to escape:

- **The fold is the authority; a carried total is a cache that happens to live in the
  log.** Any reader that must be *right* folds. `fsck` (§13) recomputes the fold and
  reports every event whose carried totals disagree with it, which is what makes the
  denormalization checkable instead of a second source of truth — and a disagreement is a
  **finding, never a repair in place** (§4.4).
- **One accumulator, called from both sides.** The writer computes the totals by calling
  the *fold's* accumulator over `(predecessor totals, this event)`, never a hand-written
  increment. Two copies that disagree is the defect this shape invites, and a
  denormalized aggregate is exactly the shape that invites a third.
- **Only pure functions of the events qualify, and only per item.** A carried value must
  be a pure function of the events up to and including its own: counts, sums, and the last
  status. Never a wall clock (§9.5), never anything read from outside the log. Per *item*
  rather than per ledger, because the writer already reads the item's max sequence to
  assign the next one (§4.1) — so the predecessor's totals arrive in a read it is making
  anyway — while a ledger-wide counter would put every item behind one number and fork on
  every branch.
- **The totals are trustworthy exactly when the item's sequence chain is unforked.** Two
  branches appending to one item both compute from the same predecessor, so after a union
  merge the tail carries totals that omit the other side. This needs no new detector: it is
  the same visible, fsck-reportable fork §4.1 already produces, and the rule is that a
  forked item's carried totals are **void until a fold restates them**. A cache with a
  known invalidation condition is safe; one without is the hand-wave.

**What the tail read costs, stated rather than implied.** Whole-ledger totals are the last
line of the current file. A single item's totals are a **reverse scan that stops at that
item's first hit** — cheap in the ordinary case, and bounded in the worst by rotation,
because §4's checkpoint at each rotation boundary carries every item's totals as of that
boundary. That last part is a **requirement on the checkpoint**, stated here rather than
assumed, because the bound depends on it: without it the reverse scan for a long-idle item
walks the whole archive. So the bound is "current file, then one checkpoint", never "the
whole history". It also narrows the index's trigger: an index earns its place when a
**cross-item** query cannot be served this way, not merely when some fold got slow.

**The second payoff is evidential.** Because the total is recorded at the moment of the
write, *what did this item's spend say when this dispatch marker was written* is
answerable without folding anything — which a snapshot holding only the present cannot
give.

## 5. Import and coexistence with a tracker being replaced

A cutover is never a big bang, because the work being tracked continues throughout. The
kit ships the three mechanisms that make one incremental, and the rules below are their
contract.

**Import** an existing tracker's JSONL export. Every extracted event carries provenance
`EXTRACTED` (§9.6) and the export's digest, and every imported record carries the
importer's own marker, so no flip point has to be kept in step with the tree.

- **The import is re-runnable, and refuses a ledger that already holds a post-cutover
  record.** A one-shot with no entry point is how a ledger drifts behind an export from the
  day after it ran, and a fresh consumer could not build one at all. The dry run reports
  how far behind the ledger is and writes nothing; it reports that same **refusal** rather
  than a count, because a preview saying "would add 200" for a run that will refuse is
  worse than no preview.
- **The order is not negotiable:** import while the other tracker is still authoritative,
  declare the residual baseline, then begin the dual write. Importing after the dual write
  has begun lets the owned side track the other one instead of being compared against it.
- **The kit's own entry point covers a record, deliberately not the graph.** Create, show
  and list, with no engine import and redaction taken as an argument. So a copied kit can
  create, read and query a work item and cannot build a dependency graph.

**Shadow mode** reads the same ledger, answers the same queries read-only, and asserts
identical verdicts for phase derivation, the ready set and gate status. Four rules, and
the first is the one that unwedged it:

- **It proves the dual write agrees, not that history agrees.** The run is judged on
  records created after the cutover; the pre-existing delta is *declared*, not compared.
- A record the **reference** holds and the ledger does not has no ledger event to classify,
  so the declaration captures that set once, at the cutover, into a committed sidecar. A
  **second declaration is refused** — re-declaring after the dual write has begun would
  absorb a genuine failure into history.
- **An empty in-scope population is inconclusive, never clean.** Until post-cutover records
  exist the run refuses to license the flip, and that refusal is correct rather than a
  defect in the instrument. `clean` and `conclusive` are two separate answers.
- A **refused reference voids the run** whatever the scoping says. The boundary decides
  which records are judged, never whether the reference was the live tracker.

**Dual-write** for one release with the other tracker still authoritative, and a write
surface with no translator **raises** rather than logging, so it stops the work instead of
silently diverging. The two defects found by using it were one mistake wearing two faces —
**a guard placed after the write cannot refuse it** — and the order that follows is decide,
then spawn, then mirror.

**Flip** the source of truth once the differential is clean and conclusive and no
unimplemented surface is in use.

### 5.1 Three risks in the import step

An export whose owner has demoted it to an interchange format — *"not the canonical
cross-machine sync channel"* — carries three consequences for an importer reading it. None
is fatal, and all three are cheaper known than discovered at the flip.

- **The export path is a second-class citizen upstream and will drift.** Pin the import
  against a known-good export and treat format drift as expected, not exceptional.
- **Import is upsert-only.** An upstream export *"cannot infer that records absent from an
  export were deleted, pruned, or simply never exported"*, so a snapshot **cannot express
  deletion** and the importer must treat tombstones as a first-class concern. §13's rule
  that an unknown event kind is preserved and skipped handles forward compatibility; this
  is the different problem of *absence*, which is ambiguous by construction in an
  upsert-only format.
- **A one-shot import is the only import.** Because the import cannot round-trip deletions,
  the differential must compare against the **live** tracker, never against a re-import of
  its export: two derivatives of one lossy snapshot agree with each other and prove
  nothing.

## 9.1 Compaction — declined

**No lossy compaction.** Git's delta plus zlib already compresses a ledger of
near-identical JSON records better than any record-shrinking scheme, and it does so
**losslessly**, which is the half compaction cannot match. Compaction discards evidence,
which is fatal to a store whose purpose is evidence.

Growth is bounded four ways instead: git compression; a rollup at the point work ships,
where the harness above the store keeps one, so a package's cost survives independently of
its detail; the event log itself, which bounds each write by the size of the change rather
than by the record's accumulated history; and **honest truncation**.

Honest truncation is the bound the other three leave out (§4.2). None of them bounds a
single pasted payload, so an agent that pastes a 5 MB log puts it in every clone —
compressed, but not removable. The per-event cap makes that ceiling explicit, and the
recorded original length is what keeps the cap from *being* the lossy compaction this
section rejects. The distinction is the whole point: compaction discards evidence after
the fact and leaves the record looking whole, while truncation drops it at the boundary
and **says on the record that it did, and by how much**. "We kept the first N bytes of a
5 MB payload" is a checkable statement that tells a reader the rest exists elsewhere; "we
summarised this" tells them neither.

The early warning to watch is **maximum line length**, not total size.

## 9.2 Ranking — a pure function of the graph

The ranking is a pure function of the graph: unblocked items only, then priority, then the
descending count of still-live blocking dependents, then the id. It deliberately **drops
creation time**, because an age-based order makes dispatch order clock-dependent for an
unchanged graph.

Two decisions the ordering does not settle on its own, recorded because they are the kind
of thing a reader re-litigates:

- The dependent count is over **blocking edges to still-live dependents** only: a
  `related` dependent was never waiting, and a closed one is work already done.
- The score packs both terms into one integer that an `explain()` decodes, so a **recorded**
  score stays readable without the graph that produced it.

**Age-freedom is structural rather than disciplinary** — the ranking's input type carries
no timestamp at all, though the ledger it is folded from does. That is the difference
between a rule and a rule nobody can break.

A recorded rank is also evidence: a dispatch marker carries the score, the rank, the
fallback rank and the **policy version**, without which a score is an uninterpretable
integer. A ranker that recommends only unclaimed work has no opinion about an
already-claimed lane, so a null rank must stay distinguishable from an unrecorded one.

## 9.4 Identity — opaque record ids, content-derived evidence ids

- **Records are mutable** — titles, descriptions and criteria are edited constantly. An id
  derived from content would either drift or lie. So a record id is **opaque and stable**: a
  short random root token, collision-checked, plus a dotted monotonic child suffix
  (`<prefix>-<root>.<n>`), which sorts naturally. Ids are never reused, and a delete leaves
  a tombstone.
- **State the collision budget rather than saying "collision-checked".** Size the id length
  from the birthday paradox, `P(collision) ≈ 1 - e^(-n²/2N)` with `N = 36^length`, against a
  declared maximum probability, and scale the length as the ledger grows. **Adaptive length
  is safe because existing ids never change** — only newly minted ones get longer.
- **Evidence is immutable** — a decision, a found-info record, a dispatch marker is a fact
  about a moment. Those ids **are** content-derived, which is what makes re-recording
  idempotent rather than duplicating.
- **No slugs in ids.** A slug embeds hyphens that read as a prefix boundary, which breaks a
  commit-message gate that parses the prefix — a shipped defect, not a hypothetical.

## 9.5 Time — a timestamp is evidence, never a constraint

Ordering comes from the log, not from the clock. The fold reads events in sequence order
(§4.1) and nothing else. Two events with equal or out-of-order timestamps are a normal
occurrence, not a conflict to resolve.

- **A write is never refused because of timestamp ordering.** Validating
  `updated_at >= created_at` hard-errors when the machine's clock steps backwards between
  two writes, which an unconverged NTP resync does routinely — turning a host's clock into
  a source of tracker failures in the middle of a landing. Record what the clock said and
  move on.
- **No derived value is a function of a timestamp.** Ranking drops creation time (§9.2);
  the same rule holds for staleness, dedup and idempotence, which key on sequence and
  content (§9.4), never on time.
- **Durations are measured on a monotonic clock.** Anything the store times itself uses a
  monotonic counter; the wall clock is only ever *recorded*.

**This was an assertion until the alternative was measured.** A production append-only
journal carrying no sequence numbers, minting event ids from the wall clock plus a random
component, has as its only total order the order its lines happen to sit in the file. In
its own published 6,467-event fixture, **44.5% of events share a millisecond** with another
event.

Three things follow. At that collision rate a millisecond timestamp **is not an ordering at
all** for nearly half the log — sorting by it yields an arbitrary permutation inside every
collided group. The order that does exist is **unrecorded**: it survives as file position,
which a union merge, a rebuild or any sort destroys silently, and nothing in the data says
the order was lost. And a harness writes in **bursts** — a multi-lane pass appends for
several lanes inside the same few milliseconds — which is precisely the shape that produces
collisions. §4.1's one integer field buys the ordering that design leaves to chance.

The general form: **the ledger must be totally ordered by something we assign, so that a
misbehaving host clock degrades the quality of our evidence and never the correctness of
our state.**

## 9.6 Provenance — every edge says how it got there

Without this, a dependency edge a human asserted, an edge an agent proposed from a
scope-glob overlap, and an edge a merge queue inferred after a conflict are
**indistinguishable in the graph** — yet only the first should be trusted, unexamined, to
gate a landing.

| Label | Meaning | Disposition |
| --- | --- | --- |
| `EXTRACTED` | explicitly asserted by a human, or mechanically derived from a fact in the repository (an import, a shared file in two scope globs) | trusted; may gate a landing |
| `INFERRED` | proposed by an agent, or deduced from a second-order signal (a bounce, a co-occurrence) | usable, but visible as a proposal |
| `AMBIGUOUS` | the derivation is uncertain | **routes a decision item**; never silently gates anything |

Three reasons this belongs in the schema rather than in a convention:

- Evidence must be attributable, and an edge is evidence about the shape of the work — the
  only kind that otherwise carries no attribution.
- It gives `AMBIGUOUS` a disposition path that already exists: an uncertain machine
  judgment belongs in the decision queue.
- It makes the coupling-edge feedback loop honest. An edge added because "the decomposition
  missed a coupling" is an inference from one observation; recording it as `INFERRED` keeps
  a later reader from mistaking it for a declared dependency, and makes *how often are our
  inferred couplings right* a question the ledger can answer.

## 12. Portability

- **No absolute paths, ever** — in any field, including provenance. A path is
  machine-specific by definition and the ledger is shared.
- **LF and UTF-8 explicitly.** A data ledger must not rely on `text=auto` heuristics: mark
  it explicitly, write newlines and UTF-8 without depending on platform defaults, and read
  tolerantly — a stray carriage return must not corrupt a fold.
- **No POSIX-only locking.** The lock must work on Windows, so no bare `fcntl`; the atomic
  temp-write-then-rename pattern is portable and is the intended mechanism (§4.4).
- **No new runtime dependency**, which is most of §4's argument: a pure-Python store
  inherits the platform matrix the host already tests rather than adding its own.
- **Nothing machine-specific in anything the kit writes or installs.** An installer that
  wrote an interpreter path and a repository path into a *tracked* file leaked a username
  into a commit and broke every teammate. Two things generalise from it. A committed
  rendering uses a host-substituted placeholder and a launcher every committer already has
  — never a bare `python3`, which on Windows hits an execution alias that opens a store
  page, a worse failure than a clean one. And **where neither a portable nor a
  machine-local rendering is possible, refuse**; falling back to the absolute one
  reinstates the bug. A kit test fixture must be *a repository containing the kit*, or the
  test pins nothing.

## 13. Failure modes and recovery

An append-only log fails differently from a database, and the differences are the design's
payoff:

| Failure | Recovery |
| --- | --- |
| Torn write (crash mid-append) | Last line is unparseable → quarantine it and report; the fold before it is intact |
| Corrupt derived index | Delete and rebuild from the log; never repaired in place |
| Bad merge (both sides appended) | Both event sets survive; the fold is order-independent for distinct events |
| Bad merge (same record edited) | Two events, both retained; conflict resolution is a *later event*, not a lost one |
| Unknown event kind (newer writer) | Preserved verbatim and skipped by the fold, with a warning |

Two commands this implies, and they are requirements rather than nice-to-haves: an
**fsck** that folds the whole log and reports anything unparseable, unknown or
referentially broken; and a **rebuild** that regenerates every derivative from the log
alone. Without them, "the log is the truth" is a claim nobody can check. They belong
together: without a check that the derivative still matches the log, a rebuild is a guess.

## 14. Testability

The properties worth asserting, beyond the differential in §5:

- **Fold determinism** — folding the same log twice yields byte-identical derivatives.
- **Order independence** — folding a shuffled log of distinct events yields the same state,
  which is what makes concurrent appends safe.
- **Idempotent replay** — re-appending an event with an existing id changes nothing.
- **Round-trip** — every field survives read-modify-write, including fields the current
  version does not understand (the upgradability requirement, tested rather than asserted).
- **Property-based generation** over event sequences, because the interesting bugs are in
  interleavings a hand-written case will not find.

## 15. Non-goals

Naming these is how the scope argument stays honest. This is not: a general-purpose issue
tracker; multi-user authentication or authorization; a sync server or hosted service; a web
application; sprint, estimation or reporting ceremony beyond what a loop consumes; a
maintained TUI; real-time collaboration; or import from third-party trackers beyond the
one-off in §5. Each is how a tool like this becomes unmaintainable, and none is required by
the loop.

One rejection is worth naming rather than listing, because it is the plausible one: **LLM
monitoring of the ledger**. It puts a paid third-party service in the store's runtime path,
which fails the test of whether a component's breaking change can be absorbed on our own
schedule — model ids are deprecated, prices change, availability is somebody else's
operational decision. It contradicts the kit boundary, which never calls the network or a
model (§4). And it is nondeterministic where every other part of this design is
deterministic: a monitor whose verdict on the *same* log can differ between two runs cannot
be a thing a gate reads. The condition it would exist to catch — a lane that has stopped
making progress — is already covered deterministically by a stall watchdog on a monotonic
clock, as §9.5 requires.
