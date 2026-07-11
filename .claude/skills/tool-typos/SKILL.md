---
name: tool-typos
description: Use typos to detect spelling mistakes in code, comments, and docs with low false positives. Trigger when proofreading source content or enforcing text quality.
---

# tool-typos

## When To Use

- Detect typo regressions in source, docs, and identifiers.
- Run quick spelling checks before commits and releases.
- Produce machine-parseable typo reports for CI pipelines.

## Trusted Commands

```bash
typos
typos src/
typos --diff
typos --write-changes
typos --type py .
typos --format json
```

## Safe Defaults

- Start with `--diff` or read-only mode before auto-fixes.
- Keep project-specific allowlists narrow in `.typos.toml`.
- Re-run after fixes to ensure clean output.

## Common Pitfalls

- Blind auto-fixes can modify intentional domain terms.
- Broad ignore lists hide genuine mistakes.
- Generated files may require explicit exclude rules.

## Output Interpretation

- Default output reports `file:line:col` and suggested correction.
- JSON format can be parsed and summarized with jq.
- Exit code 1 indicates typo findings were detected.

## Why It Matters For Agents

- Agent-generated code and docs benefit from a final spelling pass.
- Fast runtime makes it practical to run on every commit.

## Repo Conventions

- Keep user-facing docs and strings typo-free.
- Prefer fixing source terms over expanding ignore lists.

## Trigger Examples

- Should trigger: "Scan docs for misspelled command names."
- Should trigger: "Run typo checks before opening this PR."
- Should not trigger: "Query YAML values from a workflow file."
