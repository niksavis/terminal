# Worktree lifecycle

## Contents

- [Steps](#steps)
- [Hooks](#hooks)
- [Claude Code](#claude-code)
- [Protected destinations](#protected-destinations)
- [Landing lock](#landing-lock)
- [Land on CI](#land-on-ci)
- [Land through a pull request](#land-through-a-pull-request)
- [Merge several](#merge-several)

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
   An untracked file that git does not ignore, and a tracked change under a dependency path, stop ordinary cleanup.
   A symlink, and a `__pycache__` file that is not bytecode of a source beside it, also stop it.
   Rebuildable content is deleted with no copy: bytecode, recognized `.pytest_cache`, `.ruff_cache` and `.import_linter_cache` content, and the bundled Lefthook files in `build/` and `.basicly/bin` whose bytes match the pinned hashes.
   Cleanup copies every file in `.basicly/usage`, each unrecognized file in those folders and any other git-ignored file (`*.basicly-bak` backups, local config) to `.git/basicly-preserved/<lane>-<id>/` with a manifest. It checks each copy by size and hash, then removes the worktree. Dependency directories keep their own rules.
   Cleanup refuses to copy more when `.git/basicly-preserved` holds over 500 MB. Inspect that folder and remove the archives you no longer need.
   Cleanup deletes `origin/harness/<name>` when the base holds every path it changed. It keeps a branch whose head is still the commit the lane started from.
   After a CI-proven landing, `worktree merge --mode ci` runs this cleanup itself and reports a refusal with the command to finish it.
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
Use it when `gh` is logged in and the repository has a landing workflow with a `workflow_dispatch` trigger.
The landing workflows are the list `[landing] workflows = [...]` in `basicly.toml`. Without that key, the landing takes whichever of `quality-gates.yml` and `basicly-gates.yml` has the trigger; when both have it, it refuses and prints the key line to add.
It passes `base` only to a workflow that declares that input. When `gh` refuses a call, it names `gh auth login` only when `gh auth status` fails, and otherwise the exact `gh` command to rerun.
It runs locally only the `local_only` checks, because they read tracker records and CI must not.
It pushes the rebased lane to a new branch `land/NAME/N`, never a force-push, and dispatches every landing workflow on it.
It lands only when every landing workflow passes; a failed, cancelled or unfinished run refuses by name and lands nothing.
A tree that failed once gets one rerun, and the landing line says that CI passed on a rerun; after a second failure the merge refuses a new run and names both runs; change the lane first.
When git stops the merge with the lane tree staged, the merge commits it once with hooks on; a refusing hook still stops the landing and its text is shown.
After the merge it records the destination as `ci-verified`, pushes the base and deletes its `land/` branches.
It exits 1 and prints a note when the base stays unverified or unpushed, or a `land/` branch stays; that branch is listed for the owner.
If the base moved during the wait, run the merge again: a tree equal outside the ledger reuses the proof, and a code change starts a new run.
When the workflow carries the `ci-reuse` step, the push run on the base reuses the proving run and logs `ci-reuse: reuse`.
Without `gh`, or while GitHub is down, land with `--mode full`, the default.

## Land through a pull request

`basicly worktree merge NAME --bead RECORD-ID --delivery pr` lets GitHub merge the lane. `[delivery] adapter = "pr"` in `basicly.toml` makes it the default; without the key the lander above stays the default. basicly's own repository sets it, so its lanes land through pull requests, and `--delivery lander` is the fallback when GitHub is down.
It runs every check of `--mode ci` up to the proof: the record binding, the rebase, the regenerated files, the engine guard and the `local_only` checks.
It refuses a lane head that does not contain `origin/BASE`, because the pull request would then prove a tree that the base never gets. Run `git pull --ff-only` in the base checkout and merge again.
It pushes the head to a new branch `pr/NAME/HEAD12`, never a force-push, and opens a pull request or reuses the open one on the same head.
It waits for a `pull_request` run of every landing workflow on that exact head. A landing workflow without a `pull_request` trigger is refused by name. A failed run refuses and the pull request stays open.
A pull request runs again only on a new head, so a head that already failed is refused before any push. Commit a fix, or retry the same tree once with `git commit --allow-empty` or a rebase on the base.
The rerun limit counts the failed runs of every earlier `pr/NAME/` head with the same tree outside the ledger, as `--mode ci` does: a tree gets one more run after a failure, and after a second failure the lane must change. A pass only on a rerun attempt is refused.
It checks `origin/BASE` again right before the merge; when the base moved during the wait, it refuses and leaves the pull request open.
Then `gh pr merge --merge --match-head-commit HEAD` merges it on GitHub with a conventional subject that names the record. The adapter never pushes the base itself.
It checks that the merge commit has the proved tree, writes the `landing-verification` artifact for the merge commit and fast-forwards the local base.
Then it sweeps every `pr/NAME/` branch: it closes each other open pull request with a comment that names the merged one, and deletes a branch through the cleanup path when its head is on the base or the base holds every path it changed. It lists a kept branch.
`basicly worktree cleanup NAME` runs the same sweep, also after the lane worktree is gone. `close --landed COMMIT` then accepts the merge commit.
The merge queue of GitHub is not available to repositories that a user account owns, so this adapter uses required checks on the pull request.

## Merge several

```sh
basicly worktree merge-queue NAME:RECORD-ID ... [--mode M]
basicly worktree list
```
