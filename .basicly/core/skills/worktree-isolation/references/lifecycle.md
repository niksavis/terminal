# Worktree lifecycle

## Steps

1. **Create.** The worktree gets the branch `harness/<name>`, from `[worktree].base_branch` in `basicly.toml` or the current branch.
   It gets its own `.venv` (`uv sync`) and its own `node_modules`.
   The `node_modules` tree is copied from a checkout with an identical `package-lock.json`, else it comes from `npm install`.
   Neither tree is a symlink to the main checkout, so cleanup is safe.
   The command installs the repository's git hooks for every stage and refuses success when provisioning fails.
   It never reads or copies dotenv files. Names must be one portable path component.
   Failed provisioning retains the checkout, branch and session: inspect them, preserve any work, then use `cleanup` before recreating the lane.
   It refuses when `[worktree].concurrency` is reached. Read the configured value.
2. **Work.** Do the change in the worktree. Its hooks gate each commit as on the main checkout.
3. **Merge.** Under `basicly loop`, the build-to-verify advance merges for you.
   Use `merge` or `merge-queue` only for a worktree that the loop does not drive.
4. **Clean up.** `cleanup` removes the worktree, prunes the registry, and deletes `harness/<name>` when it is merged.
   It keeps an unmerged branch unless you pass `--force`. It never touches the base branch.
   It refuses locked checkouts even with `--force`; finish the active session and explicitly unlock the checkout first.
   Unknown ignored files and tracked changes under dependency paths stop ordinary cleanup. Only untracked or ignored dependency directories, the tracker redirect, and the named verify counters, run artifact and their ignore marker are disposable generated output.
   It can reclaim a worktree whose directory is gone.

## Hooks

A linked worktree's `.git` is a file. Git resolves its hooks to the shared common directory.
Provisioning installs the hooks there, so a plain `git commit` in the worktree runs every gate.

A relative override such as `git -c core.hooksPath=.git/hooks commit` resolves inside the worktree.
There `.git/hooks` does not exist, so git skips pre-commit, commit-msg and the record id check.
The commit looks clean, and the defect shows only on a later commit.
To see where hooks resolve, read the path:

```sh
git rev-parse --git-path hooks
```

## Claude Code

By default Claude Code refuses a background session's edits in the main checkout until the session enters a worktree. Setting `worktree.bgIsolation` to `"none"` lets background sessions edit the working copy without a worktree (Claude Code settings reference and worktrees page, checked 2026-11-07).
That default conflicts with sibling worktrees. Run this once per repository to set it to `none`:

```sh
basicly worktree bg-isolation
```

The command writes the committed `.claude/settings.json`, so it asks for consent. `--yes` gives that consent.

Codex and Copilot have no equivalent setting.

## Protected destinations

An agent sandbox can allow source edits while protecting `.codex`, `.agents` or the Git hook directory.
Install and landing preflight planned changes before updating the catalog, committing tracker state or rebasing.
An access refusal names the destination and the ordinary command to retry; unchanged protected outputs need no write.

For an already-authorized upgrade or landing, request task-scoped execution review for that exact command in the named checkout.
The CLI cannot escalate itself. Preserve dotenv denials, normal hooks, signing and loop checkpoints; do not broaden a machine profile.
Read the retry result and verify the repository state before continuing the loop.

## Landing lock

`basicly worktree merge` and `merge-queue` hold `.basicly/usage/landing.lock` in the main checkout while they land.
A second landing is refused with the holder's lane, record, pid and lock age; pass `--wait MINUTES` to wait for it instead.
A lock older than its 60 minute limit is reported by name and never taken.
When no landing of that lane runs any more, remove it with `basicly worktree unlock --lane LANE`; the command refuses a lock held by another lane.

## Land on CI

`basicly worktree merge NAME --bead RECORD-ID --mode ci` proves the lane on GitHub runners instead of a local full verify.
Use it when `gh` is logged in and `.github/workflows/quality-gates.yml` accepts `workflow_dispatch` with a `base` input.
It runs locally only the `local_only` checks, because they read tracker records and CI must not.
It pushes the rebased lane to a new branch `land/NAME/N`, never a force-push, and dispatches `quality-gates` on it.
It lands only on a passing run; a failed, cancelled or unfinished run refuses by name and lands nothing.
A tree that failed once gets one rerun, and the landing line says that CI passed on a rerun; after a second failure the merge refuses a new run and names both runs; change the lane first.
When git stops the merge with the lane tree staged, the merge commits it once with hooks on; a refusing hook still stops the landing and its text is shown.
After the merge it records the destination as `ci-verified`, pushes the base and deletes its `land/` branches.
It exits 1 and prints a note when the base stays unverified or unpushed, or a `land/` branch stays; that branch is listed for the owner.
If the base moved during the wait, run the merge again: a tree equal outside the ledger reuses the proof, and a code change starts a new run.
When the workflow carries the `ci-reuse` step, the push run on the base reuses the proving run and logs `ci-reuse: reuse`.
Without `gh`, or while GitHub is down, land with `--mode full`, the default.

## Merge several

```sh
basicly worktree merge-queue NAME:RECORD-ID ... [--mode M]
basicly worktree list
```
