# Model roles and their measured cost

Anthropic measured these on its own benchmarks. Source: `platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence`, read 2026-11-10. Check the page again before you rely on a number.

| Shape | Cost against Opus 5.5 alone | Score |
| --- | --- | --- |
| Opus 5.5 owner with Sonnet 5.5 subagents | about a third less | about the same |
| Opus 5.5 with a Fable advisor | about 2.1 times | 1.7 points higher, at the edge of noise |
| Fable 5.2 as orchestrator in place of Opus 5.5 | 19% more than the Opus orchestrator | about the same |
| Fable 5.2 alone | 1.5 to 2.4 times | 1.6 to 5.9 points higher |
| Haiku 5.5 subagents on coding | 32% less | about 4 points lower |

- The advisor row used Fable 5.1 as advisor. No figure exists for Fable 5.2.
- The advisor "bought about what more effort does". So raise the effort level first.
- Delegation came out ahead in two cases only: routine work with a long cost tail, and work larger than one context window. For a chain of dependent steps, the owner model alone did better.

## The advisor in Claude Code

- Turn it on for one session with `/advisor fable` or `claude --advisor fable`. The settings key is `advisorModel`.
- The main model decides when to call the advisor. A subagent inherits the advisor of its session, and its cost.
- A Fable advisor bills at Fable rates, to usage credits on a subscription plan.
- A Fable 5.2 session accepts only Fable 5.2 as advisor. `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` turns the advisor off.
- basicly configures no advisor. Turn it on for the hard problem, then turn it off with `/advisor off`.

## Known exception

The engine selects `maximum` for a loop dispatch at integrity level L3. That path belongs to `basicly loop` and does not follow this rule yet.
