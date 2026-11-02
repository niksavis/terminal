# Claude auto mode and release pushes

When a public repository tag push is blocked as creating a public surface, review the classifier denial before retrying. A project `autoMode` block has no effect: Claude reads that block from user or managed settings, or explicit invocation settings. The consumer can merge this repository-scoped example into `~/.claude/settings.json`, replacing `owner/repo` with the intended repository:

```json
{
  "autoMode": {
    "allow": ["$defaults", "Bash(git push origin v*) in owner/repo"]
  }
}
```

Keep `$defaults` when extending the classifier's default allow list. These entries are classifier guidance, not deterministic shell permission patterns. Do not install them into a consumer's user settings automatically.

Narrow `permissions.allow` rules normally resolve before the classifier and remain effective in auto mode. `autoMode.classifyAllShell` sends shell calls through the classifier even with a narrow allow; explicit deny and ask rules still take precedence. A project permission allow and a project `autoMode.allow` entry are different settings. This exception must not authorize force pushes, remote deletion or hook bypass.

Inspect the consumer's effective classifier configuration:

```sh
claude auto-mode config
```

Settings scopes and precedence: [auto-mode settings](https://code.claude.com/docs/en/auto-mode-config) and [permission modes](https://code.claude.com/docs/en/permission-modes) (checked 2026-10-27, Claude Code 2.1.312).
