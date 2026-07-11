# Source-of-Truth Projector Plan (Implementation-Ready)

> **Plan status** (2026-07-11): Phase 1 (basic implementation) is complete and passing
> quality gates. Codex target was corrected during implementation: Codex uses `AGENTS.md`
> plus `.codex/rules/*.rules`, so basicly emits only the shared `AGENTS.md` baseline for
> Codex and defers `.codex/rules/` to a future phase. Phase 2 (user customization
> extension mechanism) is planned in [source-of-truth-projector-extensions.md](source-of-truth-projector-extensions.md);
> the basic schema and directory layout are being prepared to support it without
> breaking current behavior.

## 1) Research Summary (Adopt / Adapt / Discard)

1. Adopt: Fowler's three-layer priority model (training data < conversation context < explicit priming) as the core reason to keep generated instructions explicit, short, and high-signal.
2. Adopt: Design-first discipline as a planning guardrail for this project: schema and projection mechanics are agreed before implementation details.
3. Adopt: Context anchoring as infrastructure: keep source fragments and generated outputs versioned in-repo so decisions survive session/tool boundaries.
4. Adopt: Encoding team standards as executable artifacts (not prose docs) and maintain through normal PR/CI workflow.
5. Adopt: Feedback flywheel mechanics by adding a "check" command and CI staleness gate so usage feeds back into source updates.
6. Adapt: Lattice's composability idea (small units combine) into fragment-based policy files plus target projectors.
7. Adapt: Lattice's "living context" concept into a minimal local folder for projector metadata, not a full workflow engine.
8. Adapt: Lattice's customization approach (overlay/override spirit) into simple per-target render rules and target-specific templates.
9. Discard (for now): Lattice's molecule pipeline stages (`requirement-forge` -> `design-blueprint` -> `code-forge` -> `review`) because this project is config generation infra, not task orchestration.
10. Discard (for now): plugin marketplace distribution and runtime skill invocation model; this system is local CLI only.
11. Discard (for now): any DB/server/daemon model; deterministic file-in/file-out generation is enough.
12. Gap noted: Lattice centers Claude/Cursor (and plugin packaging for Codex), while this project must support idiomatic multi-target projection including Copilot and AGENTS baseline patterns.

## 2) Scope

### 2.1 Phase 1 — Completed

- [x] Build a small CLI (Python 3.14+ with `uv`) to read source fragments and project deterministic outputs.
- [x] Support these initial targets end-to-end:
  - **Claude Code**: root `AGENTS.md` baseline, `.claude/CLAUDE.md` wrapper, and path-scoped rules under `.claude/rules/`.
  - **GitHub Copilot**: `.github/copilot-instructions.md` baseline and path-scoped instructions under `.github/instructions/`.
  - **Codex (OpenAI)**: shared `AGENTS.md` baseline only (Codex's `.codex/rules/*.rules` format is deferred).
- [x] Provide commands: `list`, `build`, `build --target <name>`, `check`.
- [x] Add a GitHub Actions CI check that fails when generated outputs are stale.
- [x] Provide a README with add-fragment and add-target instructions.
- [x] Reproduce the existing `AGENTS.md`, `.claude/CLAUDE.md`, and `.github/copilot-instructions.md` files with minimal diff, then add the generated header and stable ordering.

### 2.2 Phase 2 — Planned

- **User customization extension mechanism**: allow users to add fragments that survive
  updates to core agent configs, with verification, conflict detection, and explicit
  override semantics. Detailed in [source-of-truth-projector-extensions.md](source-of-truth-projector-extensions.md).
- **Deferred**: Cursor target, skills/hooks as first-class generated artifacts, molecule workflows, Codex `.codex/rules/*.rules` scoped rules.

## 3) Design Note (Architecture for Reviewers)

### 3.1 Core concepts

- **Fragment**: a single, tool-agnostic policy/practice/decision. One file, one purpose.
- **Target**: a coding agent ecosystem (Claude Code, Copilot, Cursor, etc.) with its own config format and activation mechanics.
- **Projector**: a target-specific renderer that selects fragments, orders them, and emits native config files.
- **Manifest**: a deterministic record of which fragments produced which output, used for CI staleness checks.

### 3.2 Why fragments instead of one shared file

The Fowler series and Lattice both argue that small, versioned, composable units beat monolithic prompts. Fragments let us:

- Author a rule once and project it to many targets.
- Evolve rules independently via normal PR review.
- Scope rules to specific paths or tools without forking the source text.

### 3.3 How targets stay idiomatic

Each target has its own Jinja2 templates and a YAML registry entry. The registry controls:

- Which fragments are selected for each output file.
- How fragments are sorted (priority, category, id).
- How path scopes map to native activation syntax (Claude `paths:`, Copilot `applyTo:`).
- Tone/density hints and soft size limits.

The source fragment body is tool-agnostic; the projector adds the target-specific framing, front matter, and ordering.

### 3.4 Fowler patterns → fragment categories

| Fowler pattern             | Fragment category                            | Purpose                                                  |
| -------------------------- | -------------------------------------------- | -------------------------------------------------------- |
| Knowledge Priming          | `project`                                    | Project defaults and priming context read before action. |
| Design-First Collaboration | `design`                                     | Design-before-code constraints and workflows.            |
| Context Anchoring          | `decisions`                                  | Anchored decisions that survive context erosion.         |
| Encoding Team Standards    | `code-style`, `testing`, `security`, `ci-cd` | Executable, versioned team standards.                    |
| Feedback Flywheel          | `commands`                                   | Commands that close the feedback loop (e.g. `check`).    |
| Tooling primitives         | `tools`, `hooks`, `skills`                   | References to tools, hooks, and reusable skills.         |
| Guardrails                 | `boundaries`                                 | Hard limits that require explicit confirmation.          |

### 3.5 Extractability and future project naming

The generator, projector, renderers, templates, and source fragments are intentionally grouped under a single top-level directory named `.basicly/` so the whole subsystem can be lifted out of this terminal repo later and distributed as its own project named **basicly**. The engine code in `.basicly/basicly/` has no hard dependency on the terminal-specific fragments in `.basicly/fragments/`; it only expects the fragment/target directory layout and schema defined in this plan. When the time comes to extract it, the move should be:

1. Copy `.basicly/basicly/` and `.basicly/templates/` into the new project.
2. Replace `.basicly/fragments/` and `.basicly/targets/` with the new project's own source content.
3. Keep the CLI interface and manifest format unchanged.

#### Standalone project names

A good name should be discoverable by engineers searching for "AI agent config generator", "Claude Copilot Cursor instructions", "source of truth prompts", or "team standards as code". It should also be distinctive enough to avoid collisions.

| Name                          | Why it works                                  | Search signals                    |
| ----------------------------- | --------------------------------------------- | --------------------------------- |
| `basicly`                     | **Selected.** Short, memorable, brandable.    | "basicly agent config"            |
| `agent-harness`               | Short, implies a control layer for agents.    | "agent harness"                   |
| `model-harness`               | Broader than agents; covers LLM tooling.      | "model harness"                   |
| `ai-harness`                  | Compact; easy to say and type.                | "AI harness"                      |
| `agent-config-projector`      | Literal; says exactly what it does.           | "agent config", "projector"       |
| `polyglot-agent-config`       | Emphasizes multi-target, idiomatic output.    | "polyglot", "agent config"        |
| `source-of-truth-projector`   | Matches the task name; clear concept.         | "source of truth", "projector"    |
| `fragment-projector`          | Highlights the fragment-based architecture.   | "fragment", "projector"           |
| `agent-instruction-projector` | SEO-friendly for instruction-file generation. | "agent instructions", "projector" |
| `multi-agent-config`          | Broad appeal; not tied to one tool.           | "multi agent", "config"           |
| `agent-config-forge`          | Active verb; suggests building/shaping.       | "agent config", "forge"           |
| `prompt-projector`            | Simple, prompt-centric.                       | "prompt", "projector"             |
| `ai-team-standards`           | Appeals to team-standard use case.            | "AI team standards"               |
| `agent-standards-projector`   | Combines standards + projection.              | "agent standards", "projector"    |
| `ai-policy-projector`         | Good for governance/searchability.            | "AI policy", "projector"          |
| `config-beam`                 | Short, memorable, implies projection.         | "config beam" (weaker SEO)        |

#### In-repo directory name candidates

Because the directory lives next to `.claude/`, `.github/`, and `.scripts/`, a dotted name signals "config/tooling" and keeps the root tidy. It also avoids polluting the package namespace with a generic word like `ai`.

| Directory name      | Pros                                                            | Cons / considerations                                      |
| ------------------- | --------------------------------------------------------------- | ---------------------------------------------------------- |
| `.basicly/`         | **Selected.** Short, brandable, mirrors `.claude/`, `.github/`. | New word; needs explanation on first encounter.            |
| `.agent-harness/`   | Clear purpose; mirrors `.claude/`, `.github/`.                  | Slightly long; package becomes `agent_harness`.            |
| `.model-harness/`   | Broader; not tied to "agent" hype cycle.                        | Less obvious that it produces agent instructions.          |
| `.ai-harness/`      | Short; easy to type.                                            | "AI" is noisy and generic; weaker identity.                |
| `.harness/`         | Minimal; generic enough to grow.                                | Too generic; collides with many existing harness concepts. |
| `.agent-config/`    | Literal; clear it is agent configuration.                       | Could be mistaken for runtime agent config, not source.    |
| `.agent-projector/` | Emphasizes the projection mechanic.                             | Less familiar term; harder to discover.                    |
| `.agent-forge/`     | Evocative; suggests shaping agent behavior.                     | Slightly abstract.                                         |
| `.agent-standards/` | Clear team-standards angle.                                     | Implies only standards, not commands/decisions.            |

**Recommendation**: use `.basicly/` as the in-repo directory. It is short, distinctive, consistent with the existing dotted config folders, and the package name `basicly` is a valid Python identifier. For the standalone project, `basicly` is also the natural GitHub repo name (`github.com/<org>/basicly`).

## 4) Source Layer Design

### 4.1 Directory layout

```text
.basicly/
  fragments/
    core/                       # shipped with basicly (phase 2)
      boundaries/
        require-explicit-confirmation.fragment.md
      code-style/
        python-style.fragment.md
      commands/
        basicly-check.fragment.md
      project/
        project-defaults.fragment.md
        core-rules.fragment.md
        quality-gate.fragment.md
        if-stuck.fragment.md
      security/
        no-secrets.fragment.md
    user/                       # user customizations (phase 2)
      # user-created fragments
    targets/
      claude.yaml
      copilot.yaml
      codex.yaml
  templates/
    claude/
      agents_md.j2
      claude_md.j2
      rule_md.j2
    copilot/
      copilot_instructions_md.j2
      instruction_md.j2
    codex/
      agents_md.j2
  basicly/
    __init__.py
    cli.py
    loader.py
    schema.py
    planner.py
    renderers/
      __init__.py
      claude.py
      copilot.py
      codex.py
      common.py
  tests/
    test_loader.py
    test_planner.py
    test_renderers.py
    test_cli.py
  generated-manifest.json
  README.md
```

**Phase 1 note**: fragments currently live directly under `.basicly/fragments/<category>/`
without the `core/` prefix. The `core/` and `user/` split is a preparatory layout for
phase 2; moving existing fragments into `core/` will happen as part of implementing the
extension mechanism.

**Naming decision**: the source root folder is `.basicly/`. It is the self-contained, extractable subsystem described in section 3.5. The Python package inside it is `.basicly/basicly/` (underscores for valid imports). Scripts and CI add `.basicly/` to `PYTHONPATH` and invoke the CLI as `python -m basicly.cli`.

**Separation of concerns within `.basicly/`**:

- `basicly/` — the engine (loader, planner, renderers, CLI). Designed to be portable to another repo.
- `templates/` — target-specific Jinja2 templates. Portable with the engine.
- `fragments/` and `targets/` — the terminal project's source content. Replaced when the engine is reused elsewhere.
- `tests/` — tests for the engine plus fixture fragments.
- `generated-manifest.json` — per-repo projection record.

### 4.2 Fragment schema

Every fragment is a Markdown file with YAML front matter between `---` markers.

#### Required fields

- `id`: stable, unique identifier. Use kebab-case. Also used as the scoped output filename stem.
- `description`: one-line summary. Used as the `description`/`paths:` front matter in scoped outputs.
- `category`: controlled enum (see 4.3).
- `applies_to`: list of target names, or `["all"]` for cross-tool baseline fragments.

#### Optional fields

- `priority`: `critical` | `high` | `medium` | `low`. Default `medium`. Sorts descending.
- `scope.paths`: list of glob strings. Default `["**"]` (always-on). Non-default globs produce path-scoped outputs.
- `tags`: list of strings for filtering and discovery.
- `status`: `active` | `draft` | `deprecated`. Default `active`. Only `active` fragments are projected.
- `title`: display heading. Default derived from `id` (kebab → title case).

#### Body

- Tool-agnostic Markdown.
- No target-specific syntax, activation front matter, or tone.
- May contain bullet lists, short paragraphs, and headings.

#### Example fragment

```markdown
---
id: python-style
description: Python style conventions for this repo.
category: code-style
priority: medium
applies_to: [all]
scope:
  paths: ["**/*.py"]
tags: [python, style]
status: active
---

- Use type hints for public functions.
- Prefer `pathlib` over `os.path`.
- Format with `ruff`.
```

### 4.3 Controlled vocabularies

**Categories** (extend only by repo convention):

- `boundaries` — guardrails requiring explicit confirmation.
- `code-style` — language/style conventions.
- `commands` — CLI commands and feedback-loop actions.
- `decisions` — anchored architectural decisions.
- `design` — design-first collaboration rules.
- `hooks` — lifecycle hook references.
- `project` — project defaults and priming context.
- `security` — secure coding rules.
- `skills` — reusable skill references.
- `testing` — testing standards.
- `tools` — tool usage conventions.
- `ci-cd` — CI/CD rules.

**Priorities** (numeric sort order):

- `critical` → 4
- `high` → 3
- `medium` → 2
- `low` → 1

**Statuses**:

- `active` — projected normally.
- `draft` — loaded but skipped during projection; useful for WIP.
- `deprecated` — skipped; kept in repo for audit trail.

### 4.4 Validation rules

The loader fails fast with file paths and line hints when it finds:

- Duplicate `id` values.
- Missing required fields.
- Unknown `category`, `priority`, or `status` values.
- `applies_to` values that are not `"all"` and not a registered target name.
- Invalid YAML front matter.

## 5) Target Registry and Projection

### 5.1 Target registry schema

Each `.basicly/targets/<name>.yaml` defines:

```yaml
name: claude
enabled: true
tone: terse_directive
max_size_warning: 8000
outputs:
  agents_baseline:
    path: AGENTS.md
    template: claude/agents_md.j2
    filter:
      applies_to: [all]
  claude_wrapper:
    path: .claude/CLAUDE.md
    template: claude/claude_md.j2
    filter:
      applies_to: [claude]
  scoped_rules:
    path_template: .claude/rules/{fragment_id}.md
    template: claude/rule_md.j2
    filter:
      applies_to: [claude]
      has_scope: true
```

Registry fields:

- `name`: target identifier. Must match a renderer module name.
- `enabled`: if `false`, the target is skipped by `build` and `check`.
- `tone`: hint for template authors; not interpreted by code in phase 1.
- `max_size_warning`: soft character-count limit; CLI logs a warning if exceeded.
- `outputs`: map of output definitions.
  - `path`: exact output path (for single-file outputs).
  - `path_template`: output path pattern using `{fragment_id}` (for per-fragment outputs).
  - `template`: Jinja2 template path under `.basicly/templates/`.
  - `filter.applies_to`: which `applies_to` values select fragments for this output.
  - `filter.has_scope`: if `true`, only fragments with non-default `scope.paths` are emitted here.

### 5.2 Selection semantics

- `applies_to: [all]` fragments are selected by any output whose `filter.applies_to` includes `all`.
- `applies_to: [claude]` fragments are selected only by outputs whose `filter.applies_to` includes `claude`.
- A fragment with `applies_to: [claude, copilot]` is selected by Claude and Copilot outputs, but **not** by the cross-tool `AGENTS.md` baseline.
- `scope.paths: ["**"]` is the default and means "always-on" (no scoped file).
- Any other `scope.paths` value means "path-scoped" and produces a scoped output file for targets that define a `scoped_*` output.

### 5.3 Sorting and determinism

Within each output, fragments are sorted by:

1. `priority` numeric value descending (critical first).
2. `category` ascending (alphabetical).
3. `id` ascending (alphabetical).

This sort is stable and deterministic. Two `build` runs with identical source produce identical output bytes.

### 5.4 Generated header

Every generated Markdown file begins with an HTML comment header:

```markdown
<!-- Generated by basicly v0.1.0. Do not edit manually. -->
<!-- Source fragments: fragment-id-1, fragment-id-2 -->
```

The header is part of the generated bytes and is included in staleness checks.

### 5.5 Manifest

`.basicly/generated-manifest.json` records:

```json
{
  "version": "1",
  "generated_at": "2026-07-11T12:34:56+00:00",
  "outputs": {
    "AGENTS.md": {
      "hash": "sha256:abc123...",
      "source_fragments": ["project-defaults", "core-rules"]
    },
    ".claude/rules/python-style.md": {
      "hash": "sha256:def456...",
      "source_fragments": ["python-style"]
    }
  }
}
```

The manifest is updated on every `build`. `check` recomputes outputs and compares both file contents and manifest entries.

## 6) Projection Details per Target

### 6.1 Claude Code

#### Claude outputs

1. `AGENTS.md` — cross-tool baseline from `applies_to: [all]` fragments.
2. `.claude/CLAUDE.md` — Claude-specific wrapper that references `AGENTS.md`, plus `applies_to: [claude]` fragments.
3. `.claude/rules/{fragment_id}.md` — one file per path-scoped fragment with `applies_to: [claude]`.

#### Claude activation mapping

- Always-on content goes into `AGENTS.md` and `.claude/CLAUDE.md`.
- Path-scoped rules use Claude Code's `paths:` front matter:

```markdown
---
description: <fragment description>
paths:
  - "**/*.py"
---
```

#### Claude tone/density

- `AGENTS.md`: directive, sectioned by category.
- `CLAUDE.md`: concise wrapper; defers to `AGENTS.md` for shared rules.
- Scoped rules: narrow, imperative, no cross-agent noise.

#### Claude size guidance

- Initial soft cap: 8,000 characters per file. To be tuned after real-world use.

### 6.2 GitHub Copilot

#### Copilot outputs

1. `.github/copilot-instructions.md` — baseline from `applies_to: [all]` and `applies_to: [copilot]` fragments.
2. `.github/instructions/{fragment_id}.instructions.md` — one file per path-scoped fragment with `applies_to: [copilot]` (or `[all]` with a non-default scope).

#### Copilot activation mapping

- Always-on content goes into `.github/copilot-instructions.md`.
- Path-scoped instructions use Copilot's `applyTo:` and `description:` front matter:

```markdown
---
description: <fragment description>
applyTo:
  - "**/*.py"
---
```

#### AGENTS.md handling

Copilot does not support `@`-style imports. Therefore the Copilot baseline **inlines** all `applies_to: [all]` fragments rather than referencing `AGENTS.md`. This preserves the "no duplication at source" rule while producing a self-contained Copilot instruction file.

#### Copilot tone/density

- Concise, explicit, checklist-friendly.
- Avoid references to other agents' config files.

#### Copilot size guidance

- Initial soft cap: 6,000 characters per file. To be tuned after real-world use.

### 6.3 Codex (OpenAI)

#### Codex outputs

1. `AGENTS.md` — cross-tool baseline from `applies_to: [all]` fragments (shared with Claude).

#### Codex activation mapping

Codex's documented convention is `AGENTS.md` plus `.codex/rules/*.rules` files. During
implementation we confirmed there is no `.codex/CODEX.md` wrapper. Basicly therefore
emits only the shared `AGENTS.md` baseline in phase 1. Path-scoped `.codex/rules/*.rules`
files are deferred to phase 2 so the correct front-matter format can be researched and
verified.

#### Codex tone/density

- `AGENTS.md`: directive, sectioned by category (shared baseline).

#### Codex size guidance

- Initial soft cap: 8,000 characters per file. To be tuned after real-world use.

## 7) CLI Specification

### 7.1 Commands

All commands run from the repository root with `.basicly/` on `PYTHONPATH`.

```bash
uv run --python-path .basicly python -m basicly.cli list
uv run --python-path .basicly python -m basicly.cli build
uv run --python-path .basicly python -m basicly.cli build --target claude
uv run --python-path .basicly python -m basicly.cli check
```

**`list`**

Prints a table of active fragments:

- `id`
- `category`
- `priority`
- `applies_to`
- `scope` (summary: `"**"` or first non-default glob)
- `status`

**`build`**

- Loads all active fragments and target registries.
- Renders outputs for all `enabled: true` targets.
- Writes a file only if its computed bytes differ from disk (preserves timestamps when unchanged).
- Updates `.basicly/generated-manifest.json`.
- Logs a warning for any output exceeding its target's `max_size_warning`.
- Exit code `0` on success, non-zero on error.

**`build --target <name>`**

- Renders only the specified target.
- Fails with a clear message if the target is unknown or disabled.
- Still updates the manifest for that target's outputs.

**`check`**

- Recomputes all enabled targets in memory.
- Compares each output's bytes to the file on disk.
- Compares the in-memory manifest to `.basicly/generated-manifest.json`.
- Prints a concise diff summary (output path, expected hash, actual hash) for any mismatch.
- Exit code `0` if everything matches, `1` if stale.
- No auto-fix in CI; the failure message tells the user to run `build`.

### 7.2 Error handling

- Invalid source: fail fast with file path and error.
- Unknown target in `--target`: list known targets and exit non-zero.
- Missing template: exit non-zero with template path.
- I/O errors: exit non-zero with exception message.

## 8) CI Gate

Add `.github/workflows/basicly.yml`:

```yaml
name: basicly

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run --python-path .basicly python -m basicly.cli check
```

The workflow fails if generated files or the manifest are stale relative to source fragments. No auto-fix is performed in CI.

## 9) Migration Path from Existing Files

The repo already has `AGENTS.md`, `.claude/CLAUDE.md`, and `.github/copilot-instructions.md`. The first `build` must reproduce those files with minimal diff.

1. Create source fragments from the existing `AGENTS.md` sections:
   - `project/project-defaults`
   - `boundaries/require-explicit-confirmation`
   - `project/core-rules`
   - `project/quality-gate`
   - `project/if-stuck`
2. Create target-specific fragments:
   - `project/claude-defaults` (`applies_to: [claude]`)
   - `project/copilot-defaults` (`applies_to: [copilot]`)
   - `project/codex-defaults` (`applies_to: [codex]`)
3. Create one path-scoped example fragment:
   - `code-style/python-style` (`applies_to: [all]`, `scope.paths: ["**/*.py"]`)
4. Run `build` and diff the generated files against the hand-authored originals.
5. Adjust fragments/templates until the diff is limited to the generated header and stable ordering.
6. Replace the hand-authored files with the generated versions and commit.
7. From then on, edit fragments only; generated files are produced by `build`.

## 10) Dependencies

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
  "pyyaml>=6.0",
  "jinja2>=3.1",
]

[dependency-groups]
dev = [
  "pytest>=8.0",
]
```

**Note**: adding dependencies requires explicit confirmation per `AGENTS.md`. These are proposed for the implementation PR.

## 11) Test Strategy

Tests live in `.basicly/tests/` and run with `uv run pytest .basicly/tests/`.

### Unit tests

- `test_loader.py`: fragment loading, front-matter parsing, validation errors.
- `test_planner.py`: fragment selection, sorting, scoped-output planning.
- `test_renderers.py`: per-target rendering, header injection, native front-matter syntax.

### Integration tests

- `test_cli.py`:
  - `build` twice with no source changes produces zero diff.
  - Editing one fragment updates only the target files that reference it.
  - `check` passes after `build` and fails after a manual edit to a generated file.
  - `build --target claude` does not touch Copilot outputs.

### Determinism fixtures

- Keep a small set of committed test fragments in `.basicly/tests/fixtures/` so tests are self-contained.

## 12) Validation Plan

- [x] Edit `project/core-rules.fragment.md` and run `build`; only `AGENTS.md` and `.github/copilot-instructions.md` change.
- [x] Edit `project/claude-defaults.fragment.md` and run `build`; only `.claude/CLAUDE.md` changes.
- [x] Edit `code-style/python-style.fragment.md` and run `build`; `AGENTS.md`, `.claude/rules/python-style.md`, and `.github/instructions/python-style.instructions.md` change.
- [x] Run `build` twice with no source changes; `git diff` is empty.
- [x] Run `check` after `build`; exits `0`.
- [x] Manually edit a generated file; run `check`; exits `1` with a clear diff summary.
- [x] Review generated Claude and Copilot files with official docs; confirm they look idiomatic.
- [ ] Review generated files with a native user of each tool in a real session (deferred).

## 13) Known Risks and Mitigations

- **Risk**: schema becomes too complex early.
  - *Mitigation*: keep required fields minimal; optional fields are ignored unless a template uses them.
- **Risk**: target idioms drift as tools evolve.
  - *Mitigation*: isolated renderers and templates per target; update one target without touching others.
- **Risk**: generated file sprawl.
  - *Mitigation*: category + priority filtering in target registry; scoped outputs only when `scope.paths` is non-default.
- **Risk**: size limits are guesses.
  - *Mitigation*: soft warnings only in phase 1; tune after measuring real outputs.
- **Risk**: migration diff is noisy.
  - *Mitigation*: iterate fragments/templates until the diff is just the generated header and stable sort.
- **Risk**: user customizations in phase 2 silently conflict with core fragments.
  - *Mitigation*: add explicit `override`/`replaces` fields and a `verify` step that reports conflicts before writing outputs.

## 14) Decisions Made (Confirm in Review)

1. **Source root**: `.basicly/` with Python package `.basicly/basicly/`.
2. **Initial targets**: Claude Code, GitHub Copilot, and Codex (OpenAI). Cursor deferred to phase 2.
3. **Source format**: Markdown fragments with YAML front matter.
4. **AGENTS.md**: fully generated from `applies_to: [all]` fragments; no hand-authored sections.
5. **Copilot baseline**: inlines `applies_to: [all]` content because Copilot cannot `@`-import `AGENTS.md`.
6. **Check mode**: byte-for-byte exactness.
7. **CI target**: GitHub Actions workflow `.github/workflows/basicly.yml`.
8. **Dependencies**: `pyyaml`, `jinja2` (runtime); `pytest` (dev).
9. **Codex correction**: basicly emits only the shared `AGENTS.md` baseline for Codex; `.codex/CODEX.md` is not a real Codex file and `.codex/rules/*.rules` is deferred.
10. **Phase 2 preparation**: fragment schema will gain `source`, `override`, `replaces`, and `extends` fields with safe defaults so user customizations can be layered on core fragments later.

## 15) Preparation for Phase 2: User Customizations

Phase 2 will let users add their own fragments that survive updates to the core agent
configs shipped with basicly. The basic implementation is being prepared with these
hooks:

- **Schema fields** (added with phase-1-safe defaults):
  - `source`: `"core"` | `"user"`. Defaults to `"core"` for backward compatibility.
  - `override`: `bool`. Defaults to `false`. When `true`, the fragment can replace
    conflicting core fragments in the generated output.
  - `replaces`: list of fragment ids. Explicit list of core fragments to remove when
    this fragment is active.
  - `extends`: list of fragment ids. Explicit list of core fragments this fragment
    augments (for documentation and conflict detection).

- **Directory layout**: `.basicly/fragments/core/` and `.basicly/fragments/user/` are
  reserved. Phase 1 keeps the flat `.basicly/fragments/<category>/` layout; phase 2
  will move core fragments under `core/` and load user fragments from `user/`.

- **Verification hook**: the planner will later accept a `verify` step that runs before
  writing outputs: detect duplicate guidance, contradictory statements, ambiguous rules,
  and scope overlaps between core and user fragments. Conflicts will be reported with
  file paths and suggested resolutions.

- **Override workflow**: when a conflict is detected, the user can either edit the user
  fragment to avoid the conflict or mark it with `override: true` (and optionally
  `replaces: [core-id]`). The build then omits the replaced core fragments from the
  generated files.

The full design is documented in [source-of-truth-projector-extensions.md](source-of-truth-projector-extensions.md).

## References

- [Fowler series hub](https://martinfowler.com/articles/reduce-friction-ai/)
- [Knowledge Priming](https://martinfowler.com/articles/reduce-friction-ai/knowledge-priming.html)
- [Design-First Collaboration](https://martinfowler.com/articles/reduce-friction-ai/design-first-collaboration.html)
- [Context Anchoring](https://martinfowler.com/articles/reduce-friction-ai/context-anchoring.html)
- [Encoding Team Standards](https://martinfowler.com/articles/reduce-friction-ai/encoding-team-standards.html)
- [Feedback Flywheel](https://martinfowler.com/articles/reduce-friction-ai/feedback-flywheel.html)
- [Lattice README](https://github.com/techygarg/lattice/blob/main/README.md)
- [Lattice how-it-works](https://github.com/techygarg/lattice/blob/main/docs/how-it-works.md)
- [Lattice origin](https://github.com/techygarg/lattice/blob/main/docs/origin.md)
