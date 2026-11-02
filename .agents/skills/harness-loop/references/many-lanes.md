# Many lanes: budget, band table, and lane watching

Reference for `basicly loop preflight` and `basicly loop supervise`.

## Task scope and optional spending limits

The user task request authorizes its lanes and their normal phase transitions.
No L-level grant or token ceiling is required before a pass starts.
Keep required verification, scope checks and destructive-action protections enabled.

Only record a token limit when the user explicitly sets one:

```sh
basicly policy budget <epic> --tokens N
```

Show the recorded limit or remove it when the user withdraws it:

```sh
basicly policy budget <epic>
basicly policy budget <epic> --clear
```

Do not invent a user budget from a forecast. Report observed usage separately from estimates.
A running dispatch can spend more before its next admission check, so report the enforcement boundary.
Historical grants remain readable; do not rewrite them to resume a task.

## What `preflight` reports

`preflight` writes nothing. Read its base state, live worktrees, runner, forecast, band table and final verdict.
A missing token limit is not a blocker. An explicit exhausted or unmeasurable limit still blocks further spend.

Resolve named readiness, dependency, scope, work-in-progress or configured-limit failures before spawning lanes.
An unknown config name or a lane selector matching no issue has its own refusal.

## The band table

Every open child gets one verdict:

| Verdict | Effect |
| --- | --- |
| `in band` | Dispatches. |
| `in band, but its scope matched no file` | Dispatches. The globs match nothing on disk. Check for a broken path or a new package. |
| `under the floor - dispatches, but merge it with a sibling` | Dispatches. The lane is too small to be worth its own. |
| `REFUSED - too large, split it` | The only verdict that refuses. |

The estimate prices every file that the scope matches, not the size of the change.
A one-line fix in a large module and a rewrite of it get the same estimate.
Do not use the band as proof that a change is large.

A `--runner manual` lane still provisions the worktree and raises a `needs input: scope` escalation.
Release it with `basicly loop answer <decision-id> "<why>"`.
Give the size of the change you measured. Say that a manual handoff has no agent context window to protect.

## Read a pass

- `lanes: 0 dispatchable now` counts adopted lanes. Before a worktree exists it reads zero, and that is not a blocker.
  The supervisor provisions from the ranked open children when the pass starts.
- A detached supervisor prints a pid and a log path. Read the log for `^routed:`, `[merged]`, `^blocked:` and `supervise exit=`.
  A launch that refuses (lock held, empty lane selection) writes the refusal on the last line of that log.
- `--max-passes` and `loop stop` both exit non-zero and write `stopped: ...` in the pass log, with the requester and the reason.
- `loop stop` writes a marker that the supervisor reads between rounds. Every dispatched lane lands. No new lane starts.
  The command prints the lanes it waits on and returns when the session ends.

## Watch a lane

A lane is a subprocess of the engine, not a subagent of your session. Use these reads:

```sh
basicly loop status <id>                                    # phase, worktree, gates, rework
basicly worktree list                                       # what is provisioned now
git -C <repo>.worktrees/<name> status --short               # is the agent editing
git -C <repo>.worktrees/<name> log --oneline main..HEAD     # has it committed
```

A worktree name replaces dots with hyphens. Issue `proj-ab1.65` provisions `proj-ab1-65`.

- **Do not poll for the process.** `pgrep -f` and `pkill -f` match the caller's own command line.
  `pkill -f "loop run <id>"` kills your own shell (exit 144) and the target survives.
  A `until ! pgrep -f ...` loop never exits and reports a finished job as still running.
  If you must, guard the pattern (`[l]oop run`) or resolve a PID first.
- **Read a landing from its summary block.** A `grep` for `[merged]` hides a failure you did not expect.
  A `tail -n` of hook output can cut the line that names the failed gate. Capture the run to a file.
