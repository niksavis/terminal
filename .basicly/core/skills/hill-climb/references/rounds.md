# Rounds

## The stop rule

The script stops the climb at the first of:

- 2 rounds in a row with no important finding, after `--refuted` is subtracted;
- no property rising 1.0 since the last round;
- the cap, 5 rounds by default; set 1 to 10 with `--cap N` on `climb-init`.

The score of a property is the lowest grade among the reviewers that graded it, so one strict reviewer can hold a climb back; the table shows `low-high` when they differ. A reviewer that misses a property still counts for the others. A property that no reviewer graded refuses the round.

After a stop, `climb-round` refuses another round. `--past-stop` allows one, only after a stop; the state records it.

## What the script refuses

- fewer than 3 or more than 6 lenses;
- a lens set in which every lens was used in the last round;
- a folder already recorded;
- a reply that is missing or malformed, or has no `grades`;
- `--refuted` below 0 or above the round's important count.
