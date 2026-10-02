# Best-practices checklist

Each rule names its source. The source is a key of `SOURCES` in `scripts/fetch_docs.py`.
A rule tagged **API only** applies only to code that calls the Claude Messages API itself.
A repository that runs the `claude` command line tool marks it "not applicable".

## Contents

- Skills
- Instruction files
- Hooks
- Subagents
- Permissions and tools
- Context and cache
- API only

## Skills

| Rule | Source |
| --- | --- |
| `name` has at most 64 characters: lowercase letters, digits and hyphens. It does not contain `anthropic` or `claude`. | skills-best-practices |
| `description` is in the third person and says what the skill does and when to use it. | skills-best-practices |
| `description` has at most 1,024 characters and no XML tag. | skills-best-practices |
| The key use case comes first. The listing cuts `description` plus `when_to_use` at 1,536 characters. | claude-code-skills |
| The body has fewer than 500 lines. Detail moves to reference files. | skills-best-practices, claude-code-skills |
| Every reference file links from `SKILL.md` directly, one level deep. | skills-best-practices |
| A reference file over 100 lines starts with a contents list. | skills-best-practices |
| The most important instructions are at the top. After a compaction, Claude Code keeps the first 5,000 tokens of each invoked skill, and 25,000 tokens for all skills together. | claude-code-skills |
| The body states what to do. It does not explain what the model already knows. | skills-best-practices |
| The body gives one default, with an alternative only where the default fails. | skills-best-practices |
| One term names one thing. No statement depends on a date. | skills-best-practices |
| A script handles its own errors and says what failed. Paths use forward slashes. The body says whether to run a script or to read it. | skills-best-practices |
| The body names each package that a script needs. | skills-best-practices |
| An MCP tool has its full name, `Server:tool`. | skills-best-practices |
| A workflow with side effects sets `disable-model-invocation: true`, so only a person starts it. | claude-code-skills |
| The skill listing fits the budget. Claude Code counts characters, at 1% of the context window by default (`skillListingBudgetFraction`). | claude-code-skills |
| At least three evaluations exist before the body grows. | skills-best-practices |

## Instruction files

| Rule | Source |
| --- | --- |
| Each `CLAUDE.md` has fewer than 200 lines. | claude-code-memory, claude-code-costs |
| A multi-step procedure, or a rule for one part of the code, moves to a skill or a path-scoped rule. | claude-code-memory |
| No two instructions contradict. The model can follow either one. | claude-code-memory |
| A rule that must always hold is a hook. An instruction is context, not enforcement. | claude-code-memory |
| An always-on file holds no timestamp, run id or other value that changes per run. The file sits in the cached prefix. | claude-code-prompt-caching, prompt-caching |
| An edit to `CLAUDE.md` takes effect after `/clear` or a restart. | claude-code-prompt-caching |

## Hooks

| Rule | Source |
| --- | --- |
| `additionalContext`, `systemMessage` and plain stdout each stay under 10,000 characters. Over the cap, the model gets a file path and a 2,000-character preview. | claude-code-hooks |
| A hook that blocks exits 2. Stderr from an exit-0 hook goes to the debug log, and the model does not see it. | claude-code-hooks |
| `additionalContext` is inside `hookSpecificOutput`, with the event name. | claude-code-hooks |
| A SessionStart hook names its matcher: `startup`, `resume`, `clear`, `compact` or `fork`. | claude-code-hooks |
| An injected reminder is short. The full instructions live in a skill or a tool description. | mid-conversation-effort-example |
| A hook filters verbose output, for example to the lines with `ERROR`. | claude-code-costs |

## Subagents

| Rule | Source |
| --- | --- |
| The `description` is short. The detail is in the system prompt. | claude-code-sub-agents |
| `tools` is declared. A subagent with no `tools` gets every tool. | claude-code-sub-agents |
| `disallowedTools` removes a tool from an inherited set. | claude-code-sub-agents |
| `skills` preloads the full text of each listed skill at startup. | claude-code-sub-agents |
| Verbose delegated work runs on a smaller model. | claude-code-costs |
| A subagent does not read the cache of its parent. A fork does. | claude-code-prompt-caching |

## Permissions and tools

| Rule | Source |
| --- | --- |
| A deny rule is scoped, such as `Bash(rm *)`. A bare tool name, `Bash(*)` or `*` removes the tool definition, and that rebuilds the cache when tool search is off. | claude-code-prompt-caching |
| An agent that can run commands and edit files works in a fixed directory with an allowlist of commands. | tool-combinations |

## Context and cache

| Rule | Source |
| --- | --- |
| Cached tokens still occupy the context window. | context-windows |
| Read the cache TTL from `claude -p "hello" --output-format json`: `usage.cache_creation.ephemeral_1h_input_tokens` and `ephemeral_5m_input_tokens`. | claude-code-prompt-caching |
| A prompt below the minimum cacheable length is not cached, and no error says so. The minimum depends on the model. | prompt-caching |
| Measure tokens on the model in use. The tokenizer of Claude Opus 4.7 and later gives about 30 percent more tokens for the same text. | token-counting |

## API only

| Rule | Source |
| --- | --- |
| Clear old tool results with context editing, and set `clear_at_least` to protect the cache. | context-editing |
| Use server-side compaction where the model supports it. | compaction |
| Append a mid-conversation system message, and do not edit the `system` field, to keep the cache. | mid-conversation-system-messages |
| Count tokens with the token-counting endpoint before a large request. | token-counting |
| Load rarely used tools with `defer_loading`, or add tool search past about 20 tools. | tool-reference, manage-tool-context |
| Keep tool definitions identical between requests. A change rebuilds the whole cache. | tool-use-with-prompt-caching |
