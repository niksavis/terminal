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
by design: that absence is what keeps it out of the model's always-loaded index.

<!-- docs-claims:begin catalog-skills -->

| Skill | Invocation | Technologies | Description |
| --- | --- | --- | --- |
| `catalog-authoring` | `model` | any | Author and improve basicly catalog sources — skills and fragments — in their YAML source format (never a discoverable .md), then project and verify them. Use when adding or editing a skill or fragment, building a catalog, or deciding where guidance should live (always-on fragment vs on-demand skill). |
| `conventional-commits` | `model` | any | Construct a valid Conventional Commits message for this repo before running `git commit`, covering type/scope, the "!" breaking-change marker, description rules, and the required trailing tracker record id. Use whenever writing or reviewing a commit message, or when a commit is rejected by the commit-msg/tracker-commit-msg hooks. |
| `decompose-plan` | `model` | any | Cut a unit of work into children the plan gate will accept — testable acceptance criteria in EARS, disjoint or declared scope globs, an acyclic dependency graph, a token budget, an integrity level, and the command that demonstrates each child end to end. Use at DECOMPOSE, when a plan gate has just refused a child, or when a child turns out to have no consumer-visible behaviour to check. |
| `falsify-first` | `model` | any | Attempt to break a claim - an invariant, a design premise, a measurement - with a concrete counterexample search before defending or adopting it, and read each kill for the precondition that carried the weight. Use before an invariant enters a plan, a design note or a gate, before a measured number becomes a claim, and whenever a candidate rule survived only because nobody attacked it. |
| `harness-client` | `model` | any | Attach to a running basicly supervisor as a second session — observe live status, present its pending decisions to a human conversationally, and record the answers. Use when a supervisor is already running (or may be) and you are not the one driving it, to check what the factory is doing, unblock a lane that waits on a judgment, or answer a queued decision. |
| `harness-loop` | `model` | any | Drive a unit of work through the basicly harness loop end-to-end (intake → classify → decompose → build → verify → validate → ship → done) with `basicly loop` over the owned tracker ledger, agent-agnostic across Claude/Codex/Copilot. Teardown is folded into the ship advance and the retro is a tracker comment; neither is a phase. Use when starting or resuming non-trivial development in a harness-enabled repo, when deciding what phase a tracked issue is in, or when coordinating the checkpoints, gates, and bounded rework the loop enforces. |
| `interface-facts` | `model` | any | Establish a fact about an external interface - a CLI flag, an API field, a model id, a price, a limit, a version - by fetching the vendor's current documentation instead of recalling it. Use before writing code, a design note, or any claim that depends on how a third-party tool behaves, and whenever a repo document already asserts such a behaviour. |
| `node` | `model` | `node` | Use Node and npm in this repo for the markdownlint git hook and other node tooling. Use when running npm or npx committing or pushing from a script or background job on WSL or debugging a node-based hook that resolves the wrong node binary. |
| `python` | `model` | `python` | Write and edit Python for this repo — type hints pathlib and cross-platform subprocess and shell-out. Use when creating or changing .py files wiring up a subprocess call chasing a test that passes on POSIX but fails only on Windows CI (a WinError 2 or a mangled backslash path) or second-guessing syntax that looks wrong for an older Python (an unparenthesized multi-exception except clause). |
| `python-guidelines` | `model` | `python` | Make the design calls no linter can check — where an oversized file splits, whether a name or docstring carries meaning, whether an abstraction earns its keep, when a suppression is legitimate, and how to satisfy a size or complexity ratchet without gaming it. Use when a size or complexity gate has just failed, before adding a noqa or nosec, when deciding what to raise and what to catch, or when shared state is reached from more than one concurrent lane. |
| `release-process` | `model` | any | Cut a release of this repository with `basicly release`, then do the three steps that command deliberately leaves to a human - deciding the version, pushing, and replacing the release page with the highlights. Use when asked to cut a release, tag a version, prepare release notes, or check whether a release published. |
| `repair-in-place` | `model` | any | Fix a named defect in the lane's own worktree, briefed with the actual findings and without re-planning or widening scope. Use at REPAIR after verify or validate failed, when a landing bounced, or whenever the temptation is to re-read the requirement and start again. |
| `root-cause` | `model` | any | Establish why something actually happened by iterating why until the answer stops changing, with each link citing an observation - and know the two ways the method lies. Use before filing a bead off a failure, before proposing a rule or a gate to prevent a recurrence, when a fix addresses a symptom, or when a retro asks for a cause. |
| `session-finish` | `model` | any | Close out a working session with a usage-statistics report, a self-improvement retro, and a pickup-clean handoff summary. Use when the user says the session is done ("wrap up", "finish the session", "close out"), before ending a long autonomous run, or whenever a summary of what changed and what the agent actually used is wanted. |
| `test-discipline` | `model` | any | Write isolated order-independent automated tests that assert on observable behavior rather than private internals. Use when writing reviewing or debugging any test (unit integration or end-to-end) in any language especially when tests share fixtures touch global or filesystem state flake depending on run order or reach into implementation details. |
| `tier-injection` | `model` | any | Install the portable tier injection kit so a subagent spawns on the model its declared tier resolves to, instead of the host default. Use when setting up tier injection in this or another repository, when a subagent ignores the tier its definition declares, or when deciding whether a host can pin a spawn's model at all. |
| `tool-ast-grep` | `user` | any |  |
| `tool-bat` | `user` | any |  |
| `tool-curl` | `user` | any |  |
| `tool-fd` | `user` | any |  |
| `tool-fzf` | `user` | any |  |
| `tool-git` | `user` | any |  |
| `tool-git-delta` | `user` | any |  |
| `tool-jq` | `user` | any |  |
| `tool-ripgrep` | `user` | any |  |
| `tool-sd` | `user` | any |  |
| `tool-shellcheck` | `user` | any |  |
| `tool-starship` | `user` | `starship` |  |
| `tool-tmux` | `user` | `tmux` |  |
| `tool-tree` | `user` | any |  |
| `tool-typos` | `user` | any |  |
| `tool-uv` | `user` | `python` |  |
| `tool-wezterm` | `user` | `wezterm` |  |
| `tool-wget` | `user` | any |  |
| `tool-xh` | `user` | any |  |
| `tool-yq` | `user` | any |  |
| `tool-zsh` | `user` | `zsh` |  |
| `validate-as-consumer` | `model` | any | Exercise a verified change the way a consumer would — in the operational environment, against the requirement that asked for it — instead of re-running the gate suite that already passed. Use at VALIDATE, before claiming a capability on a README or release note, or whenever "the tests pass" is standing in for "the feature works". |
| `work-tracker` | `model` | any | Use the owned work tracker - the append-only event ledger under .basicly/ledger/ - as the primary task/issue tracker for this repo, reading it through the kit CLI and writing it through the engine seam, and know what it refuses. Trigger when planning work, creating or claiming an issue, checking what is ready to work on, counting or querying issues in bulk, or preparing a commit that must reference a tracker issue id. |
| `worktree-isolation` | `model` | any | Isolate non-trivial work in a sibling git worktree using `basicly worktree`, covering sibling placement on a harness branch, dependency + git-hook provisioning, and safe cleanup. Use when starting a unit of work that should not touch the main checkout, when parallel tracks would collide, or when deciding whether a change needs its own worktree. |
| `wsl` | `model` | `wsl` | Configure and operate WSL (Windows Subsystem for Linux) — wsl.exe management, Windows and Linux interop and PATH gotchas, filesystem layout and performance, and how non-interactive shells differ from login shells. Use when setting up or troubleshooting WSL crossing the Windows and Linux boundary hitting slow /mnt/c file access or debugging a tool that behaves differently in a script than in your terminal. |

<!-- docs-claims:end catalog-skills -->
