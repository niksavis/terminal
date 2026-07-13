---
name: tool-ast-grep
description: Use ast-grep for structural code search and rewrite based on syntax trees. Trigger when text search is too imprecise for code-aware matching.
---

# tool-ast-grep

## When To Use

- Perform syntax-aware code search where regex is too noisy.
- Apply structural refactors with AST-level metavariables.
- Match multi-line language constructs safely.

## Trusted Commands

```bash
sg --pattern 'console.log($ARG)' --lang ts
sg --pattern 'useEffect($FN, [])' --lang tsx src/
sg --pattern 'console.log($ARG)' --rewrite 'logger.info($ARG)' --lang ts
sg --pattern '$X' --rewrite '$Y' --lang ts --interactive
sg --pattern 'def $NAME($$$ARGS): $$$BODY' --lang python
sg --json --pattern 'print($$$ARGS)' --lang python .
```

## Safe Defaults

- Always set `--lang` explicitly for predictable parsing.
- Start with search-only patterns before rewrite mode.
- Review every rewrite in git diff before staging.

## Common Pitfalls

- Binary name is `sg`, not `ast-grep`.
- `$VAR` matches one node; `$$$VARS` matches multiple nodes.
- Parse failures in malformed files can hide expected matches.

## Output Interpretation

- Default output includes file and location for each match.
- `--json` returns structured match objects with range and bindings.

## Why It Matters For Agents

- Enables safe refactors that understand syntax nesting and boundaries.
- Greatly reduces false positives compared with regex replacements.

## Repo Conventions

- Prefer ast-grep over text replacement for semantic code edits.
- Keep rewrite patterns narrow and validated against sample files.

## Trigger Examples

- Should trigger: "Replace all Python `print(...)` calls with logger calls structurally."
- Should trigger: "Find functions missing docstrings by syntax pattern."
- Should not trigger: "Download a binary release artifact over HTTP."
