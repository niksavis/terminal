# Many lanes: budget, band table, and lane watching

Reference for `basicly loop preflight` and `basicly loop supervise`.

## Size a grant budget from the ledger

Read the budget from recorded dispatches, not from an estimate of the work:

```sh
uv run python -c "
import json, statistics
d = json.load(open('.basicly/usage/run-records.json'))
ok = [r.get('tokens') or 0 for rs in d.values() for r in rs
      if r.get('agent') != 'manual' and r.get('outcome') == 'executed']
print('lanes', len(ok), 'mean', f'{statistics.mean(ok):,.0f}', 'max', f'{max(ok):,}')"
```

Set the budget to `mean x lanes`. Add headroom for one lane that stops at `runner_timeout`.
A killed lane still spends all the tokens it used before the kill.

- **"I will write the code myself" is not a budget.** `loop run` dispatches a metered runner.
  The grant level covers the checkpoints. It does not decide who writes the code.
- **The ceiling cannot stop a dispatch that has started.** The engine reads spend before a pass and records it after.
  Budget for the overshoot.

## What `preflight` reports

`preflight` writes nothing. It shows: a clean or dirty base, live worktrees, the runner and timeout,
the grant and its remaining budget, the per-lane assumption for a lane it cannot size,
the forecast if every lane starts, the band table, unpushed commits, and a `VERDICT`.

The `VERDICT: not ready - ...` line joins every blocker:

- a dirty base;
- a metered runner with no token budget (`basicly policy grant <epic> --level L2 --token-budget N`);
- a grant that is spent or cannot be metered;
- the root's own checkpoint blocks provisioning;
- no open child to provision;
- the band refuses every open child.

An unknown config name and a lane selector that names no issue return earlier with their own verdict.

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
