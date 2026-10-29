# Install flags and scopes

| Flag | Effect |
| --- | --- |
| (none) | Writes the hook into `.claude/settings.json` of this repository |
| `--user` | Writes the hook for every repository on this machine. The hook answers only in a tree that has its own committed map |
| `--dry-run` | Reports what it would write, and writes nothing |
| `--host <host>` | Installs for one host. Repeatable. The default is every known host |
| `--root <path>` | Installs into another repository |
| `--interpreter <cmd>` | Sets the command that runs the hook, for a machine with no `uv`. Example: `--interpreter "py -3"` on Windows |
| `--uninstall` | Removes only the hook that this script installed |

A second run changes nothing. It never duplicates the hook and never changes a hook that you wrote.

The two scopes get different commands. The repository file is committed and shared, so its command holds no machine-specific path. It names the hook through `${CLAUDE_PROJECT_DIR}` and runs it under `uv`:

```json
"command": "uv run --no-project --no-python-downloads python \"${CLAUDE_PROJECT_DIR}/.basicly/core/kit/tier/claude_tier_hook.py\""
```

The user file is local to the machine, so it keeps absolute paths and needs nothing on `PATH`.
