# Release refusals

## Missing release machinery

The command also needs a single-sourced `__version__ = "X.Y.Z"` line and the release scripts. The dry run refuses without them, with one of these messages:

- `no __version__ = "X.Y.Z" line found in ...`
- `changelog generator missing: ...`
- `release-note gate missing: ...`

On any of these, stop and follow the repository's own release document.

## Notes

The command refuses before the first write, and names the file, when it finds:

- an empty fragment;
- a file name that is not `<record-id>.<category>.md`;
- fragments and no `## [Unreleased]` heading;
- an `[Unreleased]` section that `carries no summary above its first ### heading`.

## Dry run

The dry run writes nothing and reports every refusal at once. It lists the fragments in the order they assemble. It refuses on:

- a dirty tree;
- a version that does not move forward;
- a tag that already exists;
- a `--date` that is not `YYYY-MM-DD`;
- an `--issue` id that the committed ledger does not hold;
- a linked worktree, because tags are shared with the primary checkout.
