# .scripts

Cross-platform scripts for this repository.

## Conventions

- Prefer Python scripts for portability across Windows, Linux, and macOS.
- Use `uv` to run scripts and tools (for example: `uv run python .scripts/<script>.py`).
- Keep scripts idempotent and non-interactive when intended for CI.
- Avoid hardcoded absolute paths and shell-specific behavior.

## Git hooks

The active local git hooks are the basicly catalog hooks (`.basicly/core/hooks/`), wired through [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) by `basicly hooks-build`. The scripts in `git-hooks/` are the repo's extended check suite; they run in the `quality-gates` CI workflow, which covers checks the basicly gates do not (pyright, bandit, markdownlint, cheat-sheet HTML), and can be run manually.

| Script                                               | Purpose                                                |
| ---------------------------------------------------- | ------------------------------------------------------ |
| [`git-hooks/pre-commit.py`](git-hooks/pre-commit.py) | ruff, pyright, bandit, markdownlint, cheat-sheet check |
| [`git-hooks/pre-push.py`](git-hooks/pre-push.py)     | pytest                                                 |

See the root [README.md](../README.md) for installation and usage instructions.
