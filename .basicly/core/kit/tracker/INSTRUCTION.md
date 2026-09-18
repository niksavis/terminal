## Work Tracker

**The append-only ledger under `.basicly/ledger/` is this repository's issue tracker.**
Read it before proposing work and write to it as work moves:

```sh
python3 .basicly/kit/tracker/cli.py ready .        # what is workable now, ranked
python3 .basicly/kit/tracker/cli.py show . <id>    # one record in full
```

Claim a record before building it, close it with a reason that names the evidence, and
reference its id in the commit message. Put a finding on the record rather than in a
comment. See the `work-tracker` skill.
