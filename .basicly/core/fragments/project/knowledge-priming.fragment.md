---
id: knowledge-priming
description: How to load repo-specific context before acting.
category: project
priority: critical
applies_to: [all]
tags: [priming, context]
status: active
---

- Before non-trivial work, look for repo-specific context (README, architecture docs, CONTRIBUTING, local overlay) and treat it as ground truth over generic assumptions.
- When repo evidence and general best practice conflict, repo evidence wins — flag the conflict instead of silently overriding it.
- If no repo-specific context exists for a decision, say so explicitly and proceed on stated assumptions; do not block on missing priming material alone.
