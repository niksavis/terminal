## Work Tracker

**Use this repository's tracker before proposing work and as work moves.**
After cloning or pulling repository setup, establish machine-local memory before implementation:

```sh
uv run --no-project --python '>=3.14' python .basicly/tracker-bootstrap.py
```

Do not implement while bootstrap refuses. Follow its runtime, setup or credential remedy.
Repository onboarding is committed once; subsequent machines run bootstrap without migrating again.
With `.basicly-tracker.toml`, the configured vault holds shared history.
`.basicly/ledger` can be a frozen guard file. Keep it intact.
Without vault configuration, `.basicly/ledger/` holds the local event log.
Read it before proposing work and write to it as work moves:

```sh
python3 .basicly/kit/tracker/cli.py ready .basicly/ledger        # what is workable now, ranked
python3 .basicly/kit/tracker/cli.py show .basicly/ledger <id> --view current # current recovery facts
python3 .basicly/kit/tracker/cli.py show .basicly/ledger <id>    # full folded detail
```

Never take work that another person or agent holds.
In vault mode, use the native claim and wait for canonical settlement before starting.
Then update its status to `in_progress` through the tracker.
Keep `BASICLY_TRACKER_SESSION` identical for tracker tools and Git hooks.
In ledger mode, claim the record and publish the ledger with the code.
Confirm observed evidence before closing. Reference the record id in the commit message.
The installed tracker includes MCP tools and the CLI. See the `work-tracker` skill.
