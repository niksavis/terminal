# Contributing

This page is for a person who changes this repository. To install the terminal setup, see the [README](../README.md).

## Repository layout

- **Terminal setup** — Python package in [`terminal_setup/`](../terminal_setup/) that detects the platform, checks prerequisites, installs tools, and deploys configs.
- **Config templates** — [`wezterm.lua`](../terminal_setup/templates/wezterm.lua), [`.tmux.conf`](../terminal_setup/templates/tmux.conf), [`.zshrc`](../terminal_setup/templates/zshrc), [`starship.toml`](../terminal_setup/templates/starship.toml), [`micro-settings.json`](../terminal_setup/templates/micro-settings.json), and [`statusline.sh`](../terminal_setup/templates/statusline.sh) (Claude Code status line).
- **Cheat sheet** — [Live HTML](https://niksavis.github.io/terminal/) and [`terminal-cheat-sheet.md`](../terminal-cheat-sheet.md) source with Linux commands, shell shortcuts, tmux controls, and WezTerm shortcuts.
- **Agent skills** — when Claude Code is installed, setup writes the basicly `cli-tools` skill into `~/.claude/skills`. It carries one reference file for each of 25 tools, so an agent picks `rg`, `fd`, `jq` and the rest in any repository and names a fallback when a tool is missing. The same skill lives in [`.claude/skills/`](../.claude/skills/) for this repository.

## Contributor setup

Only needed to change this repository. To install the terminal setup, use the [README](../README.md#install).

```bash
git clone https://github.com/niksavis/terminal.git
cd terminal
uv sync
npm install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.25.1/basicly-0.25.1-py3-none-any.whl basicly install
uvx --from https://github.com/niksavis/basicly/releases/download/v0.25.1/basicly-0.25.1-py3-none-any.whl basicly verify --mode full
uv run pytest tests/
```

Run the setup flow after your contributor environment is ready:

```bash
uv run python setup-terminal.py
```

Optional validation:

```bash
uv run python setup-terminal.py --only check
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
