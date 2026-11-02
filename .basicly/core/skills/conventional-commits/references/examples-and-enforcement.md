## Examples

Valid:

- `feat(cli): add fragment loader (app-idr)`
- `feat(cli)!: remove deprecated config format (app-idr)`
- `fix: correct sorting order (app-idr, app-abc)`
- `docs: document the update flow (app-zrj.8)`

Invalid:

| Subject | Fault | Fix |
| --- | --- | --- |
| `Fixed the bug` | no type and colon | `fix: correct the bug (app-idr)` |
| `chore(scope): Message` | uppercase description | `chore(scope): message (app-idr)` |
| `feat: support Conventional Commits marker` | uppercase proper noun | `feat: support conventional commits marker (app-idr)` |
| `fix: fix test_cli mutation bug` | underscore | `fix: fix test-cli mutation bug (app-idr)` |
| `docs: update AGENTS.md for v0.1.0` | dots and uppercase | `docs: update agents-md for the first release (app-idr)` |
| `chore: restamp the install to 0.2.0` | dots | `chore: restamp the install (app-idr)`, with `Restamp to 0.2.0.` in the body |
| `fix: correct sorting order (not an id)` | parenthetical holds no record id | a real record id |
| `chore(word description): message` | space in the scope | `chore(word-description): message (app-idr)` |

## Enforcement

The hooks are the gate. The same scripts run as the local hook and in CI:

- `.basicly/core/hooks/commit-msg.py` checks the type, the scope, the `!` and the description.
- `.basicly/core/hooks/tracker-commit-msg.py` checks that the record ids are present and exist.

The profile is stricter than Conventional Commits 1.0.0. A subject that passes plain Conventional Commits can still fail.

`basicly hooks-build` installs the pinned repository-local Lefthook binary and activates the Git launchers. Pre-push never stashes shared ledger writes. `basicly hooks-check` reports a missing hook.
