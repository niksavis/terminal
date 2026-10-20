# .scripts

Cross-platform scripts for this repository.

## Conventions

- Prefer Python scripts for portability across Windows, Linux, and macOS.
- Use `uv` to run scripts and tools (for example: `uv run python .scripts/<script>.py`).
- Keep scripts idempotent and non-interactive when intended for CI.
- Avoid hardcoded absolute paths and shell-specific behavior.

## Git hooks

The active local git hooks are the basicly catalog hooks (`.basicly/core/hooks/`), run by repository-local Lefthook 2.2.2 through [`lefthook.yml`](../lefthook.yml) and [`.basicly/lefthook.yml`](../.basicly/lefthook.yml) after `basicly hooks-build`. The scripts in `git-hooks/` are the repo's extended check suite; they run in the `quality-gates` CI workflow, which covers checks the basicly gates do not (pyright, bandit, markdownlint, cheat-sheet HTML), and can be run manually.

| Script                                               | Purpose                                                |
| ---------------------------------------------------- | ------------------------------------------------------ |
| [`git-hooks/pre-commit.py`](git-hooks/pre-commit.py) | ruff, pyright, bandit, markdownlint, cheat-sheet check |
| [`git-hooks/pre-push.py`](git-hooks/pre-push.py)     | pytest                                                 |

See the root [README.md](../README.md) for installation and usage instructions.

## Prompt and tab responsiveness checks

With Git and Starship installed, run this from the checkout:

```sh
uv run --with-editable . python .scripts/check_starship_prompt_filters.py
```

The check creates a temporary Git repository with a content clean filter. It requires an
enabled-metrics control to invoke the filter and the configured full prompt to avoid it,
while both prompts retain the branch and modified status. It does not change real
repositories or installed prompt settings. Use `--config <path>` to check another
Starship TOML. The editable install makes `terminal_setup.runner` importable because
the normal development environment has `package = false`.

With WezTerm installed, run this from the checkout:

```sh
wezterm --config-file .scripts/check_wezterm_callbacks.lua show-keys --lua
```

Require `TERMINAL_CALLBACK_CHECK_PASS` in the output. WezTerm can return exit code zero
after a configuration error and use default settings. This check loads the actual Lua
template, rejects a custom tab title callback and checks that tabs, the status footer
and the retained performance settings remain. It requires Software rendering on Windows
and WSL. It does not open a window or change an active terminal's settings.
