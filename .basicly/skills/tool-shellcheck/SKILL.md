---
name: tool-shellcheck
description: Use shellcheck to statically analyze shell scripts for bugs, portability issues, and quoting mistakes. Trigger whenever shell scripts are created or modified.
---

# tool-shellcheck

## When To Use

- Lint shell scripts for quoting, expansion, and portability issues.
- Validate generated shell snippets before execution.
- Produce structured diagnostics for script quality gates.

## Trusted Commands

```bash
shellcheck script.sh
shellcheck --shell=bash script.sh
shellcheck --format=json script.sh
shellcheck --format=gcc script.sh
shellcheck --exclude=SC2034 script.sh
echo '#!/bin/bash' | shellcheck -
shellcheck --severity=error script.sh
```

## Safe Defaults

- Run shellcheck on every changed shell script.
- Specify shell with `--shell=` when shebang is missing or ambiguous.
- Treat warnings as actionable unless there is a justified exception.

## Common Pitfalls

- SC code warnings are often real bugs, not stylistic noise.
- Scripts without shebang may be interpreted with unintended shell defaults.
- Excluding too many SC rules weakens real protections.

## Output Interpretation

- Human-readable output includes line references and SC code IDs.
- `--format=json` provides machine-parseable findings.

## Why It Matters For Agents

- Agents frequently generate shell scripts; shellcheck catches failures early.
- JSON output allows automated remediation and summary workflows.

## Repo Conventions

- Shell scripts should pass shellcheck before merge.
- Do not weaken checks to force a green run.

## Trigger Examples

- Should trigger: "Lint this installer shell script and fix warnings."
- Should trigger: "Explain why this shellcheck code appears."
- Should not trigger: "Transform this JSON payload into YAML."
