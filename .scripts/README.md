# .scripts

Cross-platform scripts for this repository.

## Conventions

- Prefer Python scripts for portability across Windows, Linux, and macOS.
- Use `uv` to run scripts and tools (for example: `uv run python .scripts/<script>.py`).
- Keep scripts idempotent and non-interactive when intended for CI.
- Avoid hardcoded absolute paths and shell-specific behavior.

## Git hooks

Scripts in `git-hooks/` are invoked by [pre-commit](https://pre-commit.com/) via [`.pre-commit-config.yaml`](../.pre-commit-config.yaml). They are kept as standalone Python files so they can be reused by lefthook or other hook managers in the future.

| Hook         | Script                                               | Purpose                             |
| ------------ | ---------------------------------------------------- | ----------------------------------- |
| `pre-commit` | [`git-hooks/pre-commit.py`](git-hooks/pre-commit.py) | ruff, pyright, bandit, markdownlint |
| `commit-msg` | [`git-hooks/commit-msg.py`](git-hooks/commit-msg.py) | Conventional commit format check    |
| `pre-push`   | [`git-hooks/pre-push.py`](git-hooks/pre-push.py)     | pytest                              |

See the root [README.md](../README.md) for installation and usage instructions.
