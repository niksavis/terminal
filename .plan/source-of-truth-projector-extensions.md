# Source-of-Truth Projector: User Customization Extension Plan

> **Status**: design phase — not yet implemented.
> **Depends on**: completed phase 1 in [source-of-truth-projector.md](source-of-truth-projector.md).

## 1) Goal

Allow users of `basicly` to add their own agent-config customizations that:

1. Survive updates to the core agent configs shipped with `basicly`.
2. Are merged into generated files (e.g. `AGENTS.md`) only after verification.
3. Are checked for duplication, ambiguity, and conflicts with core rules.
4. Can explicitly override core rules when the user chooses to keep their customization
   instead of the shipped one.

## 2) Core Concepts

| Concept           | Meaning                                                                                                        |
| ----------------- | -------------------------------------------------------------------------------------------------------------- |
| **Core fragment** | Shipped with `basicly`. Treated as read-only by users. Lives in `.basicly/fragments/core/`.                    |
| **User fragment** | Created by the user. Lives in `.basicly/fragments/user/`.                                                      |
| **Override**      | A user fragment marked to replace one or more core fragments in the generated output.                          |
| **Conflict**      | Two fragments (core/user or user/user) give contradictory or strongly overlapping guidance for the same scope. |
| **Verification**  | A pre-build analysis step that reports duplicates, conflicts, and ambiguities without writing files.           |

## 3) Schema Additions

Fragment front matter gains four optional fields. All have phase-1-safe defaults so the
basic implementation can parse them without changing current behavior.

```yaml
---
id: my-python-style
description: My team's Python conventions.
category: code-style
priority: high
applies_to: [all]
scope:
  paths: ["**/*.py"]
source: user          # "core" | "user"; default "core" for backward compatibility
override: true        # default false
replaces: [python-style]
extends: []
---

- Use single quotes for strings.
- Prefer `typing.NamedTuple` over dataclasses for small immutable records.
```

### Field reference

- `source`: `"core"` or `"user"`. In phase 2 the loader will infer this from the
  directory (`.basicly/fragments/core/` vs `.basicly/fragments/user/`) if omitted.
- `override`: when `true`, this fragment is allowed to replace core fragments. Without
  this flag, a conflict with a core fragment is treated as an error.
- `replaces`: explicit list of fragment ids to remove from the generated output when
  this fragment is active. If omitted, conflict detection may suggest replacements.
- `extends`: explicit list of fragment ids this fragment augments. Used for documentation
  and to narrow conflict detection (an extending fragment is expected to add detail, not
  contradict).

## 4) Directory Layout (Phase 2)

```text
.basicly/
  fragments/
    core/                       # shipped with basicly; treated as read-only
      boundaries/
      code-style/
      commands/
      project/
      security/
      ...
    user/                       # user customizations
      code-style/
        my-python-style.fragment.md
      project/
        my-project-defaults.fragment.md
```

**Migration from phase 1**: move existing `.basicly/fragments/<category>/` files into
`.basicly/fragments/core/<category>/`. The loader will be updated to search both
`core/` and `user/` recursively.

## 5) Selection and Override Semantics

1. Load all fragments from `core/` and `user/`.
2. Mark each fragment with its inferred `source` if the field is omitted.
3. Build the active fragment set:
   - Start with all active core fragments.
   - For each active user fragment with `replaces: [...]`, remove the listed core
     fragment ids from the set.
   - Add the user fragment to the set.
4. Run verification on the resulting set.
5. Project outputs as in phase 1.

### Override rules

- A user fragment can only replace a core fragment if `override: true` is set.
- Replacing a core fragment without `override: true` is a verification error.
- A user fragment can replace multiple core fragments.
- Two user fragments cannot replace each other; that is a verification error.
- A user fragment without `replaces` that conflicts with a core fragment must either be
  edited or marked with `override: true` (and ideally `replaces`).

## 6) Verification Pipeline

A new `verify` step runs before `build` (and is implied by `build --verify`). It reports
problems but does not write files.

### Checks

1. **Duplicate detection**
   Flag fragments whose bodies are identical or have high textual similarity (e.g.
   cosine similarity of normalized bullet text above a threshold).

2. **Contradiction detection**
   Flag pairs of fragments whose bodies contain opposing guidance for the same scope.
   Examples:
   - "Use tabs" vs "Use spaces".
   - "Prefer `pathlib`" vs "Prefer `os.path`".
   - "Always add type hints" vs "Type hints are optional".

   Phase 2 will use a small, explicit rule dictionary plus optional LLM-based semantic
   contradiction detection behind a flag.

3. **Ambiguity detection**
   Flag vague statements that are likely to conflict or be ignored, such as:
   - "Write clean code"
   - "Be reasonable"
   - "Use good judgment"

4. **Scope overlap**
   Flag two fragments with overlapping `scope.paths` but different guidance.

5. **Override validation**
   - Ensure `replaces` ids exist.
   - Ensure `replaces` only targets core fragments (or other user fragments with lower
     precedence).
   - Ensure `override: true` is present when `replaces` is used.

### Output format

```text
Verification failed: 3 issue(s)

CONFLICT  code-style/python-style (core) vs user/code-style/my-python-style
  Overlapping scope: **/*.py
  Core: "Prefer `pathlib` over `os.path`."
  User: "Prefer `os.path` over `pathlib`."
  Resolution: edit user fragment, or add `override: true` and `replaces: [python-style]`.

DUPLICATE  project/quality-gate (core) vs user/project/my-quality-gate
  Bodies are 92% similar.
  Resolution: remove the duplicate user fragment or merge differences.

AMBIGUOUS  user/project/my-project-defaults
  Line 12: "Keep code clean" is too vague to verify.
  Resolution: rewrite as a concrete, checkable rule.
```

## 7) CLI Additions

```bash
# Verify only; do not write files
uv run --python-path .basicly python -m basicly.cli verify

# Build with verification as a gate
uv run --python-path .basicly python -m basicly.cli build --verify

# List detected conflicts without building
uv run --python-path .basicly python -m basicly.cli conflicts

# List active overrides
uv run --python-path .basicly python -m basicly.cli overrides
```

### Command behavior

- `verify`: exits `0` if no issues, `1` if issues found. Prints issues grouped by type.
- `build --verify`: runs `verify` first; if it fails, no files are written.
- `conflicts`: prints only conflict-type issues.
- `overrides`: prints a table of user fragments that override core fragments, with the
  replaced ids.

## 8) Conflict Resolution Workflow

1. User creates `.basicly/fragments/user/code-style/my-python-style.fragment.md`.
2. User runs `basicly verify`.
3. System reports a conflict with core `code-style/python-style`.
4. User chooses one of:
   - **Edit** the user fragment to avoid the conflict (e.g. add guidance that does not
     contradict the core rule).
   - **Override** the core rule by adding `override: true` and
     `replaces: [python-style]` to the user fragment.
5. User re-runs `basicly verify` until it passes.
6. User runs `basicly build` to regenerate files with the override applied.

## 9) Backwards Compatibility

- Fragments without `source` default to `"core"` so existing phase-1 fragments keep
  working.
- Fragments without `override` default to `false`.
- `replaces` and `extends` default to empty lists.
- The phase-1 flat directory layout continues to work until the user opts into the
  `core/`/`user/` split.

## 10) Open Questions

1. Should contradiction detection use a static dictionary, an LLM call, or both?
2. Should `verify` be run automatically on every `build`, or only with `--verify`?
3. Should overrides be allowed to target other user fragments?
4. How should `.codex/rules/*.rules` files be represented once Codex scoped rules are
   implemented?
5. Should there be a `basicly init --user` command that scaffolds a user fragment?

## 11) Implementation Order (Proposed)

1. Move core fragments into `.basicly/fragments/core/` and load from both `core/` and
   `user/`.
2. Implement `source` inference and the new schema fields.
3. Implement override/replace logic in the planner.
4. Implement duplicate detection.
5. Implement contradiction detection (static dictionary first).
6. Implement ambiguity and scope-overlap checks.
7. Add `verify`, `conflicts`, `overrides` CLI commands and `--verify` build flag.
8. Add tests and documentation.
9. Update CI to run `basicly verify` (or `build --verify`).
