# Harness Loop

## Contents

- Rules
- Drive one issue
- Task authorization and safety
- Phases
- Gates and rework
- Before you build
- Tracker commits
- Bounded specialist work
- Many lanes
- Ship and retro
- Resume

Read this reference only for loop-managed work. Direct owner work and observer repair need no transitions.

The loop drives one tracked issue or selected parallel lanes. The current owner supplies the work and the phase inputs;
the engine records state and runs the transition checks. `--execution worker` selects headless workers.
The same commands work under Claude, Codex and Copilot.

Other skills own the mechanics of each phase: `work-tracker` (records), `worktree-isolation`
(worktrees), `decompose-plan` (child plans), `repair-in-place` (rework), `validate-as-consumer`
(validate), `conventional-commits` (commit messages).

For a deferred skill in a worker context manifest, read it with `basicly skill-read <path> --sha256 <digest>`.
A changed or missing entry needs a refreshed manifest, because a guessed skill is wrong.

## Rules

- **Read the state first with `basicly loop status <issue>`.** The ledger is the only state, so any agent can resume.
- **Commit your work on the harness branch before you advance.** The loop does not commit the agent's work.
- **Do not stage or commit tracker state for loop work.** The engine makes every tracker commit.
- **Do not record the verify gate by hand during build.** Only the build-to-verify `loop advance` merges the branch.
- **Treat the base checkout as read-only while a pass runs.** Your uncommitted files fail the lanes' landings.
- **Never clear another session's files to unblock a landing.** It destroys that session's work; hold the branch until it commits.
- **Confirm a landing from the `[merged]` line.** Every checkpoint stop exits non-zero.
- **Never signal a supervisor or its lanes.** A killed lane dies mid-write; use `--max-passes` or `loop stop`.
- **Stop on a missing required fact.** Write `.basicly/usage/needs-input.json`, because a guess becomes the record.
- **Retry a protected-destination refusal through task-scoped execution review.** `worktree-isolation` gives the retry; the loop checkpoints stay in force.

## Drive one issue

`basicly loop run` advances to the next boundary where it needs an agent or a human.
A leaf can use this sequence; owner handoffs or missing evidence can require further runs:

```sh
basicly loop status <issue>                   # phase, worktree, gates, checkpoints, rework, ready and blocked sets
basicly loop run <issue> --work-type task     # intake -> worktree ready for the agent
#   ... write the code in the worktree, then git commit it on the harness branch ...
basicly loop run <issue>                      # land, verify, validate, ship, close
```

`basicly loop advance <issue> [--work-type T] [--children plan.toml] [--mode M]` does one step.
Use it to inspect one transition. Both commands exit non-zero when the track stops short.
Pass the input that `loop status` or `loop advance` names as `needs input`.
Both also accept `--execution {session,worker}`; `session` is the default.
Other flags on both: `--runner <agent>` (`manual` gives a handoff), `--autonomy`, `--tier`.
`basicly runner list` shows which runners are available and which one `auto` selects.
`loop run` also takes `--confirm <code>`, `--root <epic>` and `--detach`.

## Task authorization and safety

The user's task request authorizes classification, decomposition and completion within its scope.
Phase transitions need no second approval, grant or token budget. Do not create a synthetic grant to make an authorized task run.
The required gates still apply, and risk classification picks them.
A task request does not authorize an unrelated destructive action; destructive-action confirmations and host permission limits stay in force.
Ask only for a missing fact, an action outside the task or a safety decision without approval.
Honor a spending limit only when the user sets one, and report observed usage.
Do not rewrite tracker events to resume old work, because the ledger is append-only.

## Phases

`loop run` does every engine step. The agent proposes the work type, writes the child plan, writes the code and commits it.

| Phase | What advances it | Commands and notes |
| --- | --- | --- |
| intake | the agent proposes the work type | `--work-type {bug,chore,task,feature,epic}`. See "Classify by shape". |
| classify | the Definition-of-Ready (DoR) gate | Continue with `basicly loop run <id>`. `basicly policy dor <id>` checks readiness. `basicly policy scaffold --type <type>` prints required headings. |
| decompose | a feature needs a child plan. A leaf goes to build. | `basicly decompose <feature> --plan plan.toml [--dry-run]`, or `--children` on advance. See `decompose-plan`. |
| decompose | the accepted plan and its readiness checks | Continue with `basicly loop run <id>` within the requested scope. |
| build | the agent commits the work on the harness branch | `basicly worktree list`. Write the code, add fragments, `git commit`, then `basicly loop advance <id>` lands it through the serial merge queue. |
| verify | the landing ran verify and recorded the required gate | Inspect with `basicly policy gate <id>`, then continue with `basicly loop run <id>`. |
| validate | a consumer-surface change needs a verdict on the merged checkout | Assesses Context, every Acceptance criterion and any distinct Requirements together. Requirements are optional unless an explicit template requires them. Blocks with `needs input: validation`. Repair a FAIL in the lane's worktree and land again. |
| ship | teardown and the closing write | `basicly loop advance <id>`. It blocks with no side effect on `needs input: demonstration` or on an unmerged branch. |

### Classify by shape

The work type decides if the loop asks for children.
One coherent change is a `task`, `bug` or `chore`.
Use `feature` only when the work fans out into children that land separately.
A `feature` blocks at decompose and provisions no worktree.
To fix a wrong type, run `basicly tracker write -- update <id> -t task` and run the loop again.

### Write a ready body

Do not guess the DoR sections. Fill the `TODO`s that `policy scaffold` prints.
A `bug` also needs `## Steps to Reproduce`. An `epic` also needs `## Success Criteria`.
Pass the body with `basicly tracker write -- create ... -d` or `basicly tracker write -- update <id> -d`.

Every later phase reads `## Scope`. Write each entry as one backticked glob on its own line:

```text
- `src/app/cli.py`
```

A bare path, or a path with a note after it, parses to no glob.
`basicly policy dor <id>` warns when `## Scope` parses to zero globs.

### Add fragments instead of editing shared files

Two lanes that edit one shared file collide at the merge. A file named with the issue id cannot collide.

| Change | Write | Instead of editing |
| --- | --- | --- |
| user-facing change | `changelog.d/<issue-id>.<category>.md`, body only, no `###` heading | `CHANGELOG.md` |
| new verify check | a `[[verify.checks]]` entry in `basicly.d/<issue-id>.toml` | `[[verify.checks]]` in `basicly.toml` |
| ratchet number moved | `[ratchet.<gate>] count_delta` or `[ratchet.<gate>.frozen]` in `basicly.d/<issue-id>.toml` | the ratchet table in `pyproject.toml` |

The category is one of `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`.
`basicly release` assembles the changelog fragments.
Write a ratchet fragment as a delta, because two lanes that each write a total fail the gate after the merge.

For a path that every lane appends to by convention, add it to `[worktree] append_only_paths`.
The engine then serializes the lanes that touch it, and `loop preflight` warns with `contend:`.
Split the shared file where you can, because serial lanes are slower.

### Verify gate

The build-to-verify `loop advance` rebases, runs verify, records the required gate and merges.
If you record the gate first (`basicly verify --mode full --issue`), the phase jumps to verify without the merge.
Ship refuses to close an issue whose branch has not landed.
After landing, reuse passing evidence only when the existing engine establishes equivalent trusted inputs.
Run affected checks locally after a failure.
Record full gate evidence in CI from the base checkout only after landing:

```sh
basicly verify --mode full --issue <id>
```

A landing by `basicly worktree merge --mode ci` records the destination as `ci-verified` from its GitHub run, so it needs no local destination verify; see `worktree-isolation`.

A dirty worktree, or a branch with no commit, blocks the landing with "commit the work on `<branch>` before landing".

## Gates and rework

Deterministic checks (tests, lint, types, build) record a required gate. A failed required gate blocks.
Semantic AI checks record an advisory gate. It never blocks.
A loop-provisioned worktree records gates in the base ledger through the redirect file.
`basicly verify --mode full --issue` refuses in a linked worktree that has no redirect.

A failed node gets a bounded rework loop (`[policy] max_rework`, default 2).
Rework is gate results and comments, not a status. At the cap, the node escalates to a human.

```sh
basicly policy rework <id> --gate verify [--record] [--allow-retry]
```

### Answer an escalation

The engine reads the first word of the answer. A reason can follow it.

```sh
basicly loop answer <decision-id> "park - the upstream fix is not released"
```

| Answer | What the engine does |
| --- | --- |
| `retry` | Gives one more attempt on that gate. A delegated answer does not give it. |
| `re-dispatch` | Nothing now. The supervisor runs the lane again on the next pass. |
| `park` or `hold` | Sets the lane `deferred` with the reason. It stops holding its parent open. Human only. |
| `land anyway` | Only for an unreliable-gate escalation. The next landing skips that gate once. Human only. |

The command prints what it did, so an answer that changed nothing is visible.

To drop a requirement, kill the lane. This destructive action still needs explicit confirmation:

```sh
basicly loop kill <id> --reason "<why this work is not done>"            # refuses and prints a code
basicly loop kill <id> --reason "<why>" --confirm <code> [--discard]
```

The kill tears the worktree down and closes the issue.
The committed work stays on the `harness/` branch unless you pass `--discard`. There is no undo.

## Before you build

- **Check a third-party claim in the issue against the real tool.** The DoR gate checks structure, not facts.
  Record the result with `basicly tracker write -- comments add <id> "verified: ..."`.
- **Check a follow-up issue against the merged code.** An issue filed after a lane overran records the lane's last position.
  Check each clause. Revert the mechanism that you think delivers it and watch named tests fail.
  Then run the real command. Close the issue with no diff when the work is done, and record the evidence.
- **Read the brief when a lane built the wrong thing.** `basicly brief <issue>` prints what the loop dispatches, with no dispatch.

## Tracker commits

The ledger is append-only. Its location follows `.basicly/ledger/redirect`, so every worktree writes the same log.
If `git diff --cached --stat` shows deletions under `.basicly/ledger/`, stop and find what rewrote it.

The engine commits tracker state at three points:

1. At provisioning, it commits the claim before it creates the worktree.
2. At landing, `loop advance` puts the `.basicly/ledger/**` changes in one `chore(tracker)` commit, then merges.
3. At ship, it commits the closing state.

Do not commit the ledger on a harness branch, because the engine commits it at landing.
Phase results and answers also write the ledger; commit it before the next landing.

The landing checks that the base checkout is clean, and it counts untracked files.
Other dirt outside the ledger blocks the landing. Check the base before every landing:

```sh
git -C <base-checkout> status --short
```

Push cadence:

- **Solo repository:** push once per track, after ship.
- **Team repository:** push each engine tracker commit at once, most of all the claim, so nobody takes claimed work.
  A claimed record with no live worktree shows a race. Compare `basicly loop status <id>` with `basicly worktree list`.

## Bounded specialist work

Delegate only by the always-on Harness Loop rule: independent work, context pressure, independent review or a specialist capability.
Give each specialist one task and a brief with its instructions, acceptance criteria, sources and done condition.
`basicly brief <issue>` previews it. Start a fresh context for unrelated work and pass the brief, not the parent conversation.
Resume a saved context only for the same task, because another task's conversation misleads it. Give each writer its own worktree.
The owner reviews and integrates the commits on a linear branch and keeps the specialist's branch.

Land committed lanes before new dispatch, because waiting work ages; the required gates still apply. The engine records completion and integration
as `[harness-policy] integration` comments; outside the engine, record them on the task yourself.
Read them with `basicly tracker show <issue>`.

## Many lanes

Use `preflight` and `supervise` over an epic for parallel work.
Only a human sets a limit on lanes. Control cost by the size of the work.
Keep two or fewer agents in the base checkout. Put every other agent in its own worktree.

```sh
basicly loop preflight <epic>                                   # read-only: can a pass start, and what does it cost
basicly loop supervise <epic> --max-passes 3 --detach           # provision, dispatch, land through the merge queue
basicly loop stop <epic> --reason "<why>" --by <name>           # finish the current round, then return
```

- **Run `preflight` first, from the base checkout.** A worktree cannot see the run records in `.basicly/usage/`.
- **Read the whole `VERDICT: not ready - ...` line.** It lists every blocker, separated by semicolons.
- **Keep fan-out within the requested scope.** The supervisor checks readiness and the plan before provisioning lanes.
- **Start a supervisor with `--detach`.** A round can outlast the timeout of the agent's shell tool.
  Read the log file it prints. Commit the ledger before you start it again.
- **Do not push while a pass holds the lock.** Read in the base. Write in your own worktree until `loop stop` returns.
- `loop stop` refuses when nothing supervises that root. A stale lock is taken only from a holder with a stale heartbeat.
- `--label <label>` fans out over the issues with that label instead of the epic's children.

Read optional spending limits, the band table, and lane observations in
[many-lanes.md](many-lanes.md).

## Ship and retro

Ship tears down the worktree and closes the issue. The merge already happened at the landing.
After an epic slice lands, write a retro comment and file a record for each finding the user keeps:

```sh
basicly tracker write -- comments add <epic-id> "Retro: <finding>"
```

## Resume

To resume after a crash or an agent switch, run `basicly loop status <issue>`.
Compare the result with `basicly worktree list`, and continue.
