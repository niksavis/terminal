---
id: no-user-path-leakage
description: Prevent committing user-specific paths, secrets, or local machine identifiers.
category: security
priority: critical
applies_to: [all]
tags: [security, privacy, data-leakage]
status: active
---

- Never commit user/customer-specific paths, usernames, home directories, hostnames, tokens, passwords, or machine-local identifiers.
- Treat terminal cwd defaults and startup directories as user-local settings: only set them from explicit user-provided install inputs.
- Keep repository defaults generic and portable; use placeholders/examples for docs instead of personal paths.
