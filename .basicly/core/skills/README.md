# basicly skill collection

This directory is the source-of-truth skill catalog for coding-agent enablement.

- Source shape: `.basicly/core/skills/<skill-name>/skill.yaml`
- Projection command: `PYTHONPATH=src uv run python -m basicly.cli skills-build`
- Default projection root: `.claude/skills`

## Catalog skills

Every source in this directory, with its own routing fields — generated and gated by
`.scripts/docs_claims.py`. A technologies-tagged source ships only to a repo that
selects that tag (`[catalog] technologies` in `basicly.toml`), so this is the catalog,
not the projection of any one consumer. A user-invoked source carries no description
field: every skill root advertises its first body paragraph instead.

<!-- docs-claims:begin catalog-skills -->

| Skill | Invocation | Technologies | Description |
| --- | --- | --- | --- |
| `best-practices-audit` | `model` | any | Audits skills, instructions, hooks, agents and permissions against the newest vendor docs. Use after a Claude Code release, or when asked if the harness still follows Anthropic guidance. |
| `catalog-authoring` | `model` | any | Authors catalog sources in YAML (always-on fragments, output styles and the skill.yaml format) and projects them. Use before editing a generated file such as SKILL.md, CLAUDE.md or AGENTS.md, or when adding a fragment or output style. |
| `cli-tools` | `model` | any | Picks the shell tool and its flags: rg, fd, jq, yq, curl, shellcheck, sd, ast-grep, typos, git, uv or tmux. Use to find files that mention a word, list files, read a JSON or YAML field, call an HTTP endpoint and show the response, or replace text. |
| `conventional-commits` | `model` | any | Writes a commit subject that passes the hooks: type, scope, breaking-change marker, record id. Use for a commit message or after a hook refused one. |
| `council` | `model` | any | Decides one closed question by independent votes of fresh agents with different stances, and reports the majority with the dissent. Use when asked to let a council, a panel or several agents vote on a choice. |
| `decompose-plan` | `model` | any | Splits an epic or feature into child tasks a build can check: EARS criteria, scope, dependencies and a demonstration command. Use to split work into tasks, or when the plan gate refuses a child. |
| `falsify-first` | `model` | any | Tries to break a claim, invariant or measurement with a concrete counterexample. Use before it enters a plan, a design or a gate, or before a high-risk number, root cause or coverage claim enters a report. |
| `find-skills` | `model` | any | Searches the catalog, then skills.sh, for an existing community skill out there, and installs one only after the user agrees. Use when asking: is there a skill for this? |
| `harness-client` | `model` | any | Attaches to a running supervisor: shows what the factory does and records answers to its decisions. Use while a supervisor runs or a lane waits on a human judgment. |
| `harness-loop` | `model` | any | Drives tracked work through the basicly loop, intake to ship. Use to start or resume work, or to move an issue past a checkpoint or gate. |
| `hill-climb` | `model` | any | Improves a plan, design, code or skill in graded rounds: fresh reviewers grade fixed properties 0 to 10, the author revises, and a script decides when to stop. Use when asked to hill-climb, iterate to a better version or improve something in rounds. |
| `interface-facts` | `model` | any | Establishes a third-party CLI flag, API field, model, price or limit from the tool and live vendor docs. Use before code depends on it. |
| `no-comments` | `model` | any | Keeps prose comments and docstrings out of code: where a fact goes instead and which tool directives stay. Use when writing a comment or docstring, or when the no-comments gate refuses a commit. |
| `node` | `model` | `node` | Runs Node and npm for the markdownlint hook and other tools. Use when npm or npx fails or resolves the wrong node binary, often on WSL. |
| `plain-english` | `model` | any | Writes plain prose for readers of any language: READMEs, release notes, design docs, records. Use when writing text for a person. |
| `python` | `model` | `python` | Writes typed Python with pathlib and Windows-safe subprocesses, and judges if an abstraction earns its keep. Use for .py edits, an except clause, a size gate or a silenced warning. |
| `release-process` | `model` | any | Cuts a release with basicly release, pushes it and confirms it published. Use when cutting, tagging or checking a release. |
| `repair-in-place` | `model` | any | Fixes a named defect in the lane's own worktree from its findings, with no new plan. Use at REPAIR after verify or validate failed. |
| `retention-probe` | `model` | any | Tests if this session still holds the always-on instruction file. Use when a repo rule seems missing, in a new subagent or after compaction. |
| `root-cause` | `model` | any | Finds the cause of a failure, a bug that came back or a test that fails intermittently, link by link with evidence, to a control this repository owns. Use when asked why something broke, keeps breaking or fails, and the cause is unclear. |
| `session-finish` | `model` | any | Summarizes what changed and what is still open. Use to wrap up a session or run a retro. Write only new recovery facts. |
| `skill-creator` | `model` | any | Writes a new skill or improves one with evals, a benchmark, graded versions and description tuning. Use when adding a new skill to the catalog, turning a workflow into a skill, comparing runs with and without a skill, or when a skill never gets picked up. |
| `swarm` | `model` | any | Runs several fresh agents on one artifact, one lens each, and merges their evidence into a verdict table; in teardown mode it also verifies, answers and fixes every finding. Use when asked for an agent swarm, several reviewers, a multi-agent review, or to tear down or find everything wrong with a diff, plan, design or document. |
| `test-discipline` | `model` | any | Writes isolated, order-independent tests that assert what the caller sees, not private helpers. Use for tests with shared fixtures, leaked state, run order or platform differences. |
| `tier-injection` | `model` | any | Chooses the model for an owner, a delegated agent, an advisor or an orchestrator, and installs the tier kit that pins it. Use when deciding which model or tier a task or subagent gets, or when a subagent ignores its tier. |
| `validate-as-consumer` | `model` | any | Runs a verified change the way a consumer does, against its requirement. Use at VALIDATE or before a README claims a capability. |
| `work-tracker` | `model` | any | Reads, files, claims and closes records in the ledger tracker. Use to plan work, check what is ready, file a bug, or claim a record before work starts. |
| `worktree-isolation` | `model` | any | Isolates work in a sibling git worktree, then merges and cleans up. Use to keep a change out of the main checkout or when parallel tracks collide. |
| `wsl` | `model` | `wsl` | Operates WSL: wsl.exe, interop, PATH, slow /mnt/c. Use when crossing Windows and Linux, or when a tool works in a terminal but not from a script. |

<!-- docs-claims:end catalog-skills -->
