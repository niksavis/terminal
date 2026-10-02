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
| `best-practices-audit` | `model` | any | Audits skills, instructions, hooks, agents and permissions against the newest vendor docs. Use after a Claude Code or Codex release. |
| `catalog-authoring` | `model` | any | Authors catalog sources (skills, fragments, styles) in YAML and projects them. Use when adding a new skill or fragment to the catalog. |
| `cli-tools` | `model` | any | Picks the fast tool for a shell task: rg to find every file that mentions a word, fd to list files, jq or yq for a JSON or YAML field, curl for an HTTP endpoint. |
| `conventional-commits` | `model` | any | Writes a commit subject that passes the hooks: type, scope, breaking-change marker, record id. Use for a commit message or after a hook refused one. |
| `decompose-plan` | `model` | any | Cuts work into children the plan gate accepts: EARS criteria, scope globs, budgets, a demo command. Use at DECOMPOSE or when a plan gate refuses a child. |
| `falsify-first` | `model` | any | Tries to break a claim, invariant or measurement with a concrete counterexample. Use before it enters a plan, a design or a gate. |
| `find-skills` | `model` | any | Searches the catalog, then skills.sh, for an existing community skill out there, and installs one only after the user agrees. Use when asking: is there a skill for this? |
| `harness-client` | `model` | any | Attaches to a running supervisor: shows what the factory is doing and records answers to its decisions. Use while a supervisor runs or waits. |
| `harness-loop` | `model` | any | Drives tracked work through the basicly loop, intake to ship. Use to start or resume work, or to move an issue past a checkpoint or gate. |
| `interface-facts` | `model` | any | Establishes a third-party CLI flag, API field, model, price or limit from the tool and live vendor docs. Use before code depends on it. |
| `no-comments` | `model` | any | Edits code in a repo that bans prose comments: where a fact goes, which directives stay. Use when editing code or when the no-comments gate refuses. |
| `node` | `model` | `node` | Runs Node and npm for the markdownlint hook and other node tools. Use when npm or npx fails or resolves the wrong node binary, often on WSL. |
| `plain-english` | `model` | any | Writes plain prose for readers of any language: READMEs, release notes, design docs, records. Use when writing text for a person. |
| `python` | `model` | `python` | Writes typed Python with pathlib and Windows-safe subprocesses, and judges whether an abstraction earns its keep. Use for .py edits, an except clause, a size gate or a silenced warning. |
| `release-process` | `model` | any | Cuts a release with basicly release, pushes it and confirms it published. Use when cutting, tagging or checking a release. |
| `repair-in-place` | `model` | any | Fixes a named defect in the lane's own worktree from its findings, with no new plan. Use at REPAIR after verify or validate failed. |
| `retention-probe` | `model` | any | Tests if this session still holds the always-on instruction file. Use when a repo rule seems missing, in a new subagent or after compaction. |
| `root-cause` | `model` | any | Finds why a failure happened, with evidence for each why, and names the control that refuses it. Use after a failure, before a fix or a gate. |
| `session-finish` | `model` | any | Closes a session with a usage report, a retro and a handover of what changed and what is open. Use when the user wraps up or a long run ends. |
| `skill-creator` | `model` | any | Writes a new skill or improves one with evals, a benchmark, graded versions and trigger tuning. Use when turning a workflow into a skill. |
| `test-discipline` | `model` | any | Writes isolated, order-independent tests that assert what the caller sees, not private helpers. Use for tests with shared fixtures, leaked state or run order. |
| `tier-injection` | `model` | any | Installs the tier kit so a subagent runs on the model its tier names. Use when a host must pin the model of a spawn or a subagent ignores its tier. |
| `validate-as-consumer` | `model` | any | Runs a verified change the way a consumer does, against its requirement. Use at VALIDATE or before a README claims a capability. |
| `work-tracker` | `model` | any | Reads, files, claims and closes records in the ledger tracker. Use to plan work, check what is ready, file a bug or claim an issue. |
| `worktree-isolation` | `model` | any | Isolates work in a sibling git worktree, then merges and cleans up. Use to keep a change out of the main checkout or when parallel tracks collide. |
| `wsl` | `model` | `wsl` | Operates WSL: wsl.exe, interop, PATH, slow /mnt/c. Use when crossing Windows and Linux, or when a tool works in a terminal but not from a script. |

<!-- docs-claims:end catalog-skills -->
