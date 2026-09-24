## Work Tracker

**The append-only ledger under `.basicly/ledger/` is this repository's issue tracker.**
Read it before proposing work and write to it as work moves:

```sh
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger        # what is workable now, ranked
python3 .basicly/kit/tracker/cli.py show .basicly/ledger <id>    # one record in full
```

Many people share this tracker: never take a story that `ready` shows as held. Reserve a
story with `assign` before you plan it, `claim` it when you start, and push the ledger at
once. Close a record with a reason that names the evidence, and reference its id in the
commit message. Put a finding on the record rather than in a
comment. See the `work-tracker` skill.
