---
id: secure-coding
description: Secure-coding checklist covering trust boundaries, secrets, and data leakage.
category: security
priority: critical
applies_to: [all]
tags: [security, privacy, data-leakage]
status: active
---

- Validate and sanitize all external input at trust boundaries before it reaches business logic.
- Parameterize database queries and shell commands; never build them by concatenating untrusted input.
- Never commit secrets (keys, tokens, passwords, connection strings); use env vars or a secret manager and keep them out of logs.
- Don't leak internal detail (stack traces, queries, paths) in user-facing errors; log server-side, return a generic message.
- Verify authorization at the service layer, not just the UI or controller entry point.
- Never commit user- or machine-specific paths, usernames, or hostnames; keep repo defaults generic and portable.
