# Bounded waiting

Read this before you wait for a long command or CI. Use the host's bounded wait, because each
extra model turn that prints an unchanged status costs a full round trip.

## Keep one command

- Start a command or CI watcher once and keep the handle it returns.
- Wait for completion in that call when it fits; otherwise read the same handle again with a bounded wait. An empty read is not completion.
- Keep each wait inside the host's responsiveness limits.
- Report the real exit status. A live handle with no status is still running, and no handle and no status is unresolved. Show a nonzero result or a cancellation, and save useful failure output.
- Cancel only your own command, through the host's cancellation call, and confirm that it ended. A cancel request or a lost connection does not prove that the process stopped.
- Return a short excerpt when the status changes, not the unchanged log.
- Keep one watcher. A CLI watcher polls its service without a model turn per poll.

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

The cleared handle stops a second wait after completion. These names are host calls, not shell commands.
A bounded wait does not wake an idle session; a completion notice needs host support and a live wake-up test.
