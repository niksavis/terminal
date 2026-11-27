# Contributing

This page is for a person who changes this repository. To install the terminal setup, see the [README](../README.md).

## Repository layout

- **Terminal setup** — Python package in [`terminal_setup/`](../terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](../terminal_setup/templates/wezterm.lua), [`.tmux.conf`](../terminal_setup/templates/tmux.conf), [`.zshrc`](../terminal_setup/templates/zshrc), [`starship.toml`](../terminal_setup/templates/starship.toml), [`micro-settings.json`](../terminal_setup/templates/micro-settings.json), and [`statusline.sh`](../terminal_setup/templates/statusline.sh) (Claude Code status line).
- **Cheat sheet** — [Live HTML](https://niksavis.github.io/terminal/) and [`terminal-cheat-sheet.md`](../terminal-cheat-sheet.md) source with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Agent skills** — when Claude Code is installed, setup writes the basicly `cli-tools` skill into `~/.claude/skills`. It carries one reference file for each of 22 tools, so an agent picks `rg`, `fd`, `jq` and the rest in any repository and names a fallback when a tool is missing. The same skill lives in [`.claude/skills/`](../.claude/skills/) for this repository.

## Contributor setup

Only needed to change this repository. To install the terminal setup, use the [README](../README.md#install).

```bash
git clone https://github.com/niksavis/terminal.git
cd terminal
uv sync
npm install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.49.6/basicly-0.49.6-py3-none-any.whl basicly install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.49.6/basicly-0.49.6-py3-none-any.whl basicly verify --mode full
uv run pytest tests/
```

When `basicly install` moves the basicly pin, refresh the `cli-tools` skill that the setup package carries, and commit it with the install:

```bash
uv run python .scripts/bundle_cli_tools_skill.py
```

The pre-push hook runs `uv run python .scripts/bundle_cli_tools_skill.py --check`. It fails when the bundled files differ from the skill of the pinned basicly version, and names each file. On a local push without the pinned wheel in the uv cache, it prints one line and skips; CI always runs it.

Run the setup flow after your contributor environment is ready:

If you use the same Windows checkout from WSL, give WSL a separate virtual
environment. Windows and Linux cannot share the checkout's `.venv`:

```bash
UV_PROJECT_ENVIRONMENT="$HOME/.cache/terminal-dev-venv" uv run pytest tests/
```

The Windows commands can continue to use their default `.venv`.

```bash
uv run python setup-terminal.py
```

Optional validation:

```bash
uv run python setup-terminal.py --only report
uv run python setup-terminal.py --dry-run
uv run python setup-terminal.py --only report
```

Once that is done, run the test suite and checks manually with:

```bash
uv run pytest tests/
uv run python .scripts/git-hooks/pre-commit.py
```

## VS Code

Workspace settings, recommended extensions, tasks, and launch configs are committed in [`.vscode/`](../.vscode/). Open the repo in VS Code and install the recommended extensions when prompted.

## Releases

The release process is in [Releases](releases.md). The cheat sheet publishing is in [Cheat sheet publishing](cheat-sheet-publishing.md).
