---
id: require-explicit-confirmation
description: Actions that require explicit user confirmation before proceeding.
category: boundaries
priority: critical
applies_to: [all]
tags: [guardrails, confirmation]
status: active
---

- Force-push, history rewrite, or destructive git resets.
- Deleting files/branches/data beyond explicit task scope.
- Editing CI/CD, deployment, infra-as-code, ignore/secrets files, or `.env*`.
- Adding/removing/upgrading dependencies.
- New network calls outside task scope.
- Skipping or weakening tests/lint/type checks to force success.
