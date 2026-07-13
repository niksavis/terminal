---
id: no-user-path-leakage
description: Terminal-specific rule that cwd defaults and startup directories are user-local settings.
category: security
priority: critical
applies_to: [all]
tags: [security, privacy, data-leakage]
extends: [secure-coding]
status: active
---

- Treat terminal cwd defaults and startup directories as user-local settings: only set them from explicit user-provided install inputs.
- Use placeholders/examples for personal paths in docs.
