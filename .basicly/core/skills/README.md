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
| `catalog-authoring` | `model` | any | Author and improve basicly catalog sources — skills, fragments and output styles — in their YAML source format (never a discoverable .md), then project and verify them. Use when you add or edit a skill or fragment, build a catalog, or decide where guidance should live (always-on fragment or on-demand skill). |
| `cli-tools` | `model` | any | Pick the installed command-line tool for a shell task instead of a slower default - rg to search text in files, fd to find or list files by name or extension, bat to read a file with line numbers, jq or yq to read a field from a JSON or YAML file, sd to replace text, ast-grep for code structure, xh or curl to call an HTTP endpoint, just for project recipes. Use when you search, list, read or reshape files or data, call an API or run a project task; then load tool-<name> for its flags. |
| `conventional-commits` | `model` | any | Construct a Conventional Commits subject that passes the commit-msg and tracker-commit-msg hooks on the first attempt - type, scope, the "!" breaking-change marker, the lowercase description and the trailing tracker record id. Use when you write or review a commit message, or when a hook rejected a commit. |
| `decompose-plan` | `model` | any | Cut a unit of work into children that the plan gate accepts, each with EARS acceptance criteria, disjoint or declared scope globs, acyclic dependencies, a token budget, an integrity level and an end-to-end demonstration command. Use at DECOMPOSE, when a plan gate refused a child, or when a child has no consumer-visible behaviour to check. |
| `falsify-first` | `model` | any | Attempt to break a claim - an invariant, a design premise, a measurement - with a concrete counterexample search before you defend or adopt it, and read each kill for the precondition that carried the weight. Use before an invariant enters a plan, a design note or a gate, or before a measured number becomes a claim. |
| `harness-client` | `model` | any | Attach to a running basicly supervisor as a second session, observe its live status, present its pending decisions to a human and record the answers. Use when a supervisor is already running or may be, to check what the factory is doing, unblock a lane that waits on a judgment, or answer a queued decision. |
| `harness-loop` | `model` | any | Drive tracked work through the basicly harness loop (intake, classify, decompose, build, verify, validate, ship) with `basicly loop`, for one issue or many lanes under a supervisor. Use when you start or resume non-trivial development, decide which phase an issue is in, or advance it past a checkpoint, gate or rework. |
| `interface-facts` | `model` | any | Establish a fact about an external interface - a CLI flag, an API field, a model id, a price, a limit, a version - from the installed binary and the vendor's current documentation, never from recall. Use before code or a claim depends on how a third-party tool behaves. |
| `no-comments` | `model` | any | Write and edit code files in a repository that bans prose comments: where a fact goes instead, which directive comments stay, and the commands that report and remove prose. Use when you create or edit any code file, or when the no-comments gate refuses a change. |
| `node` | `model` | `node` | Use Node and npm for the markdownlint git hook and other node tooling. Use when you install npm packages, run npm or npx from a script or background job on WSL, or debug a node-based hook that resolves the wrong node binary. |
| `plain-english` | `model` | any | Write or revise prose a person will read — a README, a release note, a landing page, a design document, a tracker record. Use when the wording must stay plain for readers who do not share the writer's language or culture, and to strip marketing phrasing from a heading. |
| `python` | `model` | `python` | Write and edit Python with type hints, pathlib and cross-platform subprocess calls. Use when you create or change .py files, wire up a subprocess call, chase a test that fails only on Windows CI (a WinError 2 or a mangled backslash path), or doubt a multi-exception except clause that looks wrong for an older Python. |
| `python-guidelines` | `model` | `python` | Make the design decisions that no linter checks, such as where an oversized file splits, whether an abstraction earns its keep and when to silence a warning. Use when a size or complexity gate fails, before you add a noqa or nosec suppression, when you decide what to raise and catch, or when concurrent lanes share state. |
| `release-process` | `model` | any | Cut a release of this repository with `basicly release`, then do the steps that command leaves to a person - choose the version, write the summary, push, and confirm the release published. Use when asked to cut a release, tag a version, prepare release notes, or check whether a release published. |
| `repair-in-place` | `model` | any | Fix a named defect in the lane's own worktree from the actual findings, without a new plan or a wider scope. Use at REPAIR after verify or validate failed, when a landing bounced, or when you want to re-read the requirement and start again. |
| `retention-probe` | `model` | any | Test whether this session still holds the repository's always-on instruction file in its context window. Use when a repo convention seems to have gone missing, at the start of work in a subagent or a fresh worktree, or after a compaction, before you trust that project rules are loaded. |
| `root-cause` | `model` | any | Establish why something happened by asking why until the answer stops changing, with an observation for each link, and name the control that would have refused it. Use before you file a record or propose a gate after a failure, when a fix treats a symptom, or when a retro asks for a cause. |
| `session-finish` | `model` | any | Close out a working session with a usage-statistics report, a self-improvement retro and a clean handoff summary of what changed and what is still open. Use when the user says the session is done ("wrap up", "finish for today", "close out"), or before a long autonomous run ends. |
| `test-discipline` | `model` | any | Write isolated, order-independent tests that assert on observable behavior, not private internals. Use when you write, review or debug a test in any language, especially when tests share fixtures, touch global or filesystem state, fail by run order, or reach into implementation details. |
| `tier-injection` | `model` | any | Install the portable tier injection kit so a subagent spawns on the model its declared tier resolves to, not on the host default. Use when you set up tier injection in this or another repository, when a subagent ignores the tier its definition declares, or when you decide whether a host can pin the model of a spawn. |
| `tool-ast-grep` | `user` | any | |
| `tool-bat` | `user` | any | |
| `tool-curl` | `user` | any | |
| `tool-direnv` | `user` | any | |
| `tool-fd` | `user` | any | |
| `tool-fzf` | `user` | any | |
| `tool-git` | `user` | any | |
| `tool-git-delta` | `user` | any | |
| `tool-git-lfs` | `user` | any | |
| `tool-jq` | `user` | any | |
| `tool-just` | `user` | any | |
| `tool-lazygit` | `user` | any | |
| `tool-ripgrep` | `user` | any | |
| `tool-sd` | `user` | any | |
| `tool-shellcheck` | `user` | any | |
| `tool-starship` | `user` | `starship` | |
| `tool-tmux` | `user` | `tmux` | |
| `tool-tree` | `user` | any | |
| `tool-typos` | `user` | any | |
| `tool-uv` | `user` | `python` | |
| `tool-wezterm` | `user` | `wezterm` | |
| `tool-wget` | `user` | any | |
| `tool-xh` | `user` | any | |
| `tool-yq` | `user` | any | |
| `tool-zsh` | `user` | `zsh` | |
| `validate-as-consumer` | `model` | any | Exercise a verified change the way a consumer does, in the operational environment and against the requirement that asked for it, instead of re-running the gate suite. Use at VALIDATE, before you claim a capability in a README or release note, or when "the tests pass" stands in for "the feature works". |
| `work-tracker` | `model` | any | Read, file, claim, refine and close records in the owned work tracker, the append-only event ledger in .basicly/ledger/. Use when you plan work, check what is ready to pick up, file a bug or issue, query the tracker in bulk, or write a commit that names a record id. |
| `worktree-isolation` | `model` | any | Isolate non-trivial work in a sibling git worktree on a harness branch with `basicly worktree`, with dependency and git-hook provisioning, merge and safe cleanup. Use when work must stay out of the main checkout, when parallel tracks would collide, or when you decide if a change needs its own worktree. |
| `wsl` | `model` | `wsl` | Configure and operate WSL (Windows Subsystem for Linux): wsl.exe management, Windows and Linux interop, PATH, filesystem speed and non-interactive shells. Use when you set up or troubleshoot WSL, cross the Windows and Linux boundary, hit slow /mnt/c file access, or a tool works in your terminal but not from a script. |

<!-- docs-claims:end catalog-skills -->
