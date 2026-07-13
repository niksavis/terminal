---
id: non-interactive-shell
description: Avoid shell commands that hang waiting on interactive confirmation.
category: tools
priority: medium
applies_to: [all]
tags: [shell, tooling]
status: active
---

- Prefer cross-platform implementations over shell-specific behavior when a choice exists.
- Use non-interactive flags (`cp -f`, `mv -f`, `rm -f`, package-manager `-y`, `ssh -o BatchMode=yes`) for ops that can hang on a prompt — some shells alias these to interactive mode.
