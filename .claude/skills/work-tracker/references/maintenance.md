## Import from another tracker

```sh
basicly tracker import .beads/issues.jsonl --source beads --dry-run   # writes nothing
basicly tracker import .beads/issues.jsonl --source beads
```

- The import keeps the source ids, so old commit messages still resolve.
- It copies unknown source fields without change.
- It is an upsert. It reports a field that disagrees and does not change it.
- Absence is not a deletion. Pass `--deleted <id>` for a record you confirmed deleted.
- It rejects by name an id that the commit hook would refuse, and imports the rest. The
  exit code is not zero when it refused something, so read the report.
- A second run is a replay, so a partial import completes and does not double.

## Fold the writer shards

A writer appends to `pending-<branch>.jsonl`, never to the trunk log, so two branches do
not conflict. Every read folds the shards with the trunk log. A fold only limits the file
count:

```sh
basicly tracker fold
```

- Run it as its own pull request when `fsck` warns about the shard count, or when the hook
  reports pending shards.
- It refuses while the tree has a change outside the ledger. Commit your work first.
- Its commit takes a record id from the events in the shard, so the commit hook admits it.
- `[tracker] fold_on_merge = true` opts into a read-only post-merge reminder on the
  default branch. It reports the explicit command without folding, staging or committing.
  The loop folds shards at its explicit tracker commit boundaries. Run a manual fold
  outside Git hooks; a hook must never create another commit.

## Bulk queries with `jq`

- **`record` holds the record id, and `id` holds the event id** (`<record>#ev-<hash>`).
  `select(.id=="<record>")` matches nothing.
- **The body of a record is in the payload of its `created` event.** The other kinds
  (`comment`, `status`, `field`, `edge`, `gate`) carry only their own fact.
- **A folded record nests its fields under `fields`.** That is the shape of `show` and
  `list`, not of the raw payload.

```sh
jq -c 'select(.record=="<id>" and .kind=="created").payload' .basicly/ledger/events-*.jsonl .basicly/ledger/pending-*.jsonl
jq -r 'select(.kind=="created")|.record' .basicly/ledger/events-*.jsonl .basicly/ledger/pending-*.jsonl | sort -u | wc -l
jq -r '.kind' .basicly/ledger/events-*.jsonl .basicly/ledger/pending-*.jsonl | sort | uniq -c   # positive control
```

Run the positive control before you report a zero. An empty result can also mean a wrong
key.
