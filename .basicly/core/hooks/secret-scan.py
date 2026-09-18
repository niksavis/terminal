from __future__ import annotations

import re
import subprocess  # nosec B404
import sys

ALLOWLIST_PRAGMA = "pragma: allowlist secret"

_GENERIC_RULE = "generic-secret-assignment"

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("github-token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("slack-webhook", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}")),
    (
        "teams-webhook",
        re.compile(r"https://[A-Za-z0-9.-]+\.webhook\.office\.com/[A-Za-z0-9@/._-]{10,}"),
    ),
    ("telegram-bot-token", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("google-api-key", re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        _GENERIC_RULE,
        re.compile(
            r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key"
            r"|private[_-]?key|client[_-]?secret|bearer|credential|webhook"
            r"|connection[_-]?string)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
    ),
)

_PLACEHOLDER = re.compile(
    r"(?i)example|changeme|placeholder|redacted|dummy|sample|your[-_ ]"
    r"|<[^>]+>|x{4,}|\.\.\.|test[-_]?(?:value|secret|token|key|password)"
)


def rule_hit(text: str) -> str | None:
    if ALLOWLIST_PRAGMA in text:
        return None
    for name, pattern in _RULES:
        if pattern.search(text):
            if name == _GENERIC_RULE and _PLACEHOLDER.search(text):
                continue
            return name
    return None


def staged_added_lines() -> list[tuple[str, int, str]]:

    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    added: list[tuple[str, int, str]] = []
    path: str | None = None
    lineno = 0
    in_hunk = False
    for line in proc.stdout.splitlines():
        if line.startswith("diff --git"):
            path, in_hunk = None, False
        elif not in_hunk and line.startswith("+++ "):
            target = line[4:]
            path = None if target == "/dev/null" else target[2:] if target[:2] == "b/" else target
        elif line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            lineno = int(match.group(1)) if match else 0
            in_hunk = True
        elif in_hunk and line.startswith("+") and path is not None:
            added.append((path, lineno, line[1:]))
            lineno += 1
    return added


def main() -> int:
    findings = [
        (path, lineno, rule)
        for path, lineno, text in staged_added_lines()
        if (rule := rule_hit(text))
    ]
    if not findings:
        return 0
    print("secret-scan: possible secret(s) in staged content — commit blocked.", file=sys.stderr)
    for path, lineno, rule in findings:
        print(f"  {path}:{lineno}: {rule}", file=sys.stderr)
    print(
        f"Remove the secret, or if it is a false positive add a "
        f"'{ALLOWLIST_PRAGMA}' comment on the line.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
