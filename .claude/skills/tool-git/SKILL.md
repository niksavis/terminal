---
name: tool-git
description: Use git for repository state inspection, safe staging, diff review, and history-aware change management. Trigger when the task involves commits, branches, diffs, or version control decisions.
---

# tool-git

## When To Use

- Inspect working tree state and commit history.
- Review and stage focused diffs before commit.
- Compare branches and verify what changed.

## Trusted Commands

```bash
git status --short
git --no-pager diff
git --no-pager diff --staged
git --no-pager log --oneline -n 20
git --no-pager show HEAD
git add path/to/file
git restore --staged path/to/file
```

## Safe Defaults

- Use `--no-pager` in non-interactive contexts.
- Stage only task-relevant files.
- Check status before and after edits to avoid accidental scope creep.

## Common Pitfalls

- Mixing unrelated edits into one commit.
- Using destructive reset/checkout patterns without explicit approval.
- Misreading staged vs unstaged columns in short status output.

## Output Interpretation

- `??` indicates untracked files.
- Left/right `M` columns in short status represent index/worktree changes.

## Why It Matters For Agents

- Git state determines safe automation and review boundaries.
- High-signal diff workflows prevent accidental regressions.

## Repo Conventions

- Never rewrite history or run destructive git commands without explicit confirmation.
- Keep diffs minimal and avoid unrelated reformatting.

## Trigger Examples

- Should trigger: "Review my staged diff for regressions before commit."
- Should trigger: "Show what changed in this branch compared to main."
- Should not trigger: "Lint this shell script for POSIX issues."
