# A worked example

```text
Signal      3 of 5 lanes failed to land on one shared anchor, twice in one pass
Why 1       the rebase conflicted            (the merge result names the conflict)
Why 2       two lanes appended at one anchor (both scope globs name basicly.toml)
Why 3       decompose grouped the work by scope-glob overlap, which is file adjacency
Why 4       scope globs are the only structure the decomposer can see
STOP        we control that

Branch not taken: "generate the anchors". Real, but it fixes three files, not the
slicing rule that keeps producing collisions.

Control     a plan-gate refusal when two children declare an overlapping anchor
Tier        control
Covers      every decomposition that slices by file adjacency
```
