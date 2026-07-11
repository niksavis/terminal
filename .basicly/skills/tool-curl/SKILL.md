---
name: tool-curl
description: Use curl for low-level HTTP requests, headers, and data transfer debugging. Trigger when APIs, webhooks, download checks, or protocol-level diagnostics are required.
---

# tool-curl

## When To Use

- Run low-level HTTP diagnostics with explicit flags.
- Inspect response codes, headers, redirects, and payloads.
- Download artifacts in deterministic script-friendly ways.

## Trusted Commands

```bash
curl -fsSL https://example.com
curl -I https://example.com
curl -fsSLo output.bin https://example.com/file.bin
curl -fsS -w '%{http_code}\n' -o /dev/null https://example.com
curl -fsS -H 'Accept: application/json' https://example.com/api
curl -fsS -X POST -H 'Content-Type: application/json' -d '{"name":"demo"}' https://example.com/api
```

## Safe Defaults

- Use `-f` to fail on HTTP errors.
- Use `-sS` to reduce noise while preserving errors.
- Use `-L` when redirects are expected.

## Common Pitfalls

- Unquoted URLs with `?` or `&` can be mangled by the shell.
- Secrets can leak via verbose output or command history.
- Implicit content negotiation can cause confusing response formats.

## Output Interpretation

- Exit code `22` with `-f` indicates HTTP status >= 400.
- `-I` returns headers only for quick health checks.
- `-w` can emit status/metrics for script decisions.

## Why It Matters For Agents

- curl remains the most portable HTTP primitive across platforms.
- Precise flag control enables reliable debugging and automation.

## Repo Conventions

- Avoid adding network calls beyond stated task scope.
- Keep examples token-safe and never embed credentials.

## Trigger Examples

- Should trigger: "Check whether this endpoint returns a 302 redirect."
- Should trigger: "Download a release binary in a setup script."
- Should not trigger: "Search all Python files for a class name."
