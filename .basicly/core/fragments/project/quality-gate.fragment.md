---
id: quality-gate
description: Quality gate rules before finishing work.
category: project
priority: high
applies_to: [all]
tags: [quality, review]
status: active
---

- Review the diff before finishing; do not mark complete with "should work" — verify.
- Run the checks this repo already enforces (tests, lint, type check, hooks/CI config) for anything the change touches — point at existing gates, don't restate what they check.
- Before declaring a change done, exercise it the way it will actually be used (run the command, read the generated output, call the changed function/endpoint) — passing tests is not the same as having used the feature.
- If a gate can't be run, say so explicitly instead of skipping it silently.
