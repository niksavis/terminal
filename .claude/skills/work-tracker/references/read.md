## Read

When a broader orientation is useful, use the report that takes no id. For an existing
task, read its current record and latest handover directly. Its first line is the newest note
tagged `[session handover <date>]`:

```sh
basicly session start                     # last handover, ready, blocked, live grants, decision targets
```

Then ask one question at a time. These commands find the ledger themselves:

```sh
basicly tracker ready --limit 10          # the ranked ready set: what to work on now
basicly tracker blocked                   # each dispatchable record that is not ready, and why
basicly tracker stats                     # totals by status
basicly tracker show <id> --view current  # current fields, clarifications and latest handoffs
basicly tracker show <id>                 # full folded detail and note history, as JSON
basicly tracker list --status open        # the set, as JSON
basicly tracker items --json              # one slim item per record, for a tool that reads them
basicly tracker describe --json           # the adapter description: watch globs, writes, statuses
```

The current view keeps every ordinary clarification and the latest handoff per kind and
writer, including concurrent handoffs. It does not assert a complete original contract.
For omitted handoffs or process detail, run `basicly tracker show <id> --view history
--snapshot <snapshot_identity>` with the identity the current view returned. A changed
record refuses stale retrieval. Source truncation remains explicit and cannot be undone
by a longer read. No new state store or summary note is written by these reads.

These reads run no code from the repository. `write`, `import`, `scrub`, `fold` and
`serve` run the repository's tracker kit.

`ready` ranks by priority, then by the number of records that depend on each one. A
record with children is an anchor, not the work, so it is never ready. `ready` leaves
out every record labelled `refine` or failing `dor`. Pass acceptance criteria and requirements as `--acceptance` and `--requirements`;
a description that holds either heading is refused.

The loop views answer about one unit:

```sh
basicly loop status <id>                  # phase, worktree, gates, checkpoints, rework
basicly policy gate <id>                  # required gates and their recorded results
basicly policy dor <id>                   # Definition of Ready
```

For an older run, inspect compatibility state only when needed. These reads are not authorization prerequisites:

```sh
basicly policy grant <id>
basicly policy checkpoint <id> classify
```

The user task request authorizes normal work; do not issue another grant to resume it.

The kit CLI does the same with no engine. Its first positional is always the ledger
directory:

```sh
python3 .basicly/core/kit/tracker/cli.py ready .basicly/ledger
python3 .basicly/core/kit/tracker/cli.py show .basicly/ledger <id>
python3 .basicly/core/kit/tracker/cli.py list .basicly/ledger --status open --summary --limit 20
python3 .basicly/core/kit/tracker/cli.py list .basicly/ledger --summary --query "<words>"
python3 .basicly/core/kit/tracker/cli.py fields .basicly/ledger      # each field, its role and its reader
```

## Show a person the state

```sh
basicly tracker serve                     # page and HTTP API on 127.0.0.1:8765; --host, --port, --web
```

When a board serves, write an id as a link to `/record/<id>` on it. Make sure that the
port answers before you link, and name the port. A link to a dead port is worse than the
bare id.
