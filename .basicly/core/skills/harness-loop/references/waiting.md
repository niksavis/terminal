# Bounded waiting

Read this before waiting for a long-running command or CI. Prefer the host's bounded
execution or continuation call so an unfinished command does not cause repeated model
turns just to print unchanged status.

## Keep one command

- Start a command or CI watcher once. Retain the execution handle it actually returns.
- When the command fits the allowed wait, wait for completion in that call. Otherwise,
  continue reading the same handle with a bounded wait. An empty read is not completion.
- Keep the wait below higher-priority responsiveness and update limits. Do not extend
  those limits through repository guidance.
- Report the actual exit status. A live handle without an exit status means still
  running; missing both is unresolved. Zero means success, and a nonzero result or
  cancellation must remain visible. Save useful failure output.
- Cancel only the owned command through the host's cancellation API or supported signal.
  Confirm termination; losing a connection is not proof that the process stopped.
- Return a bounded status excerpt when it changes rather than the complete unchanged log.

A CLI watcher can poll its service without involving the model on every poll. That is
different from repeatedly returning to the model to ask whether the watcher finished.
Keep the existing watcher rather than creating another one for each observation.

## Hosts exposing the Codex session tools

Some hosts expose `functions.exec`, `tools.exec_command` and `tools.write_stdin`.
These are host APIs, not shell commands or universal Codex CLI flags. Follow the actual
host schema. Keep the outer tool yield longer than the inner wait, within the allowed
responsiveness limit.

After a command returns a live integer `session_id`, save that actual value with
`store("wait_session_id", result.session_id)`. Then run this through `functions.exec`:

```javascript
// @exec: {"yield_time_ms": 25000}
const sessionId = load("wait_session_id");
if (!Number.isInteger(sessionId)) {
  throw new Error("No running command handle; inspect the original result first.");
}
const result = await tools.write_stdin({
  session_id: sessionId,
  chars: "",
  yield_time_ms: 20000,
  max_output_tokens: 1000,
});
if (result.exit_code !== undefined) store("wait_session_id", null);
text(result);
```

The cleared handle prevents another wait after observed completion. Other hosts need
their equivalent wait and cancellation APIs; do not copy these names into a shell.
Bounded waiting does not provide automatic wake-up from an idle model session. Native
completion notifications require a supported host integration and a live wake-up test.
