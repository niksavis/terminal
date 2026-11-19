from __future__ import annotations

import re
from collections.abc import Callable

GENERIC_RULE = "generic-secret-assignment"

SECRET_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
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
        GENERIC_RULE,
        re.compile(
            r"(?i)(?:password|passwd|secret|token|api[_-]?key|access[_-]?key"
            r"|private[_-]?key|client[_-]?secret|bearer|credential|webhook"
            r"|connection[_-]?string)\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
    ),
)

PLACEHOLDER = re.compile(
    r"(?i)example|changeme|placeholder|redacted|dummy|sample|your[-_ ]"
    r"|<[^>]+>|x{4,}|\.\.\.|test[-_]?(?:value|secret|token|key|password)"
)

_PATH_TAIL = r"[^\s\"'`,;)\]}]*"

MACHINE_PATH_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("posix-home-path", re.compile(rf"/(?:home|Users)/[A-Za-z0-9._-]+{_PATH_TAIL}")),
    ("windows-unc-path", re.compile(rf"\\\\\?\\[A-Za-z]:\\{_PATH_TAIL}")),
    ("windows-drive-path", re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:\\[^\s\"'`,;)\]}]+")),
)

ABSOLUTE_PATH_RULE = (
    "posix-absolute-path",
    re.compile(r"(?<![\w.~:/<-])/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]*"),
)

_ENV_ASSIGNMENT = r"[A-Z][A-Z0-9_]*=\S*"
_DUMP_RUN = 8
_CREDENTIAL_NAME = r"[A-Z0-9_]*(?:TOKEN|SECRET|KEY|PASSWORD|PASSWD)"
_CREDENTIAL_VALUE = r"""(?:'[^']{4,}'|"[^"]{4,}"|\S{4,})"""

ENVIRONMENT_DUMP_RULE = "environment-dump"
ENV_CREDENTIAL_RULE = "env-credential-assignment"
DUMP_PATTERN = re.compile(rf"(?:{_ENV_ASSIGNMENT}\s+){{{_DUMP_RUN - 1},}}{_ENV_ASSIGNMENT}")
CREDENTIAL_PATTERN = re.compile(rf"(?<![A-Za-z0-9_])({_CREDENTIAL_NAME}=)({_CREDENTIAL_VALUE})")


def marker(rule: str) -> str:
    return f"<redacted:{rule}>"


def _secret(rule: str) -> Callable[[re.Match[str]], str]:
    def substitute(match: re.Match[str]) -> str:
        if rule == GENERIC_RULE and PLACEHOLDER.search(match.group(0)):
            return match.group(0)
        return marker(rule)

    return substitute


def _credential(match: re.Match[str]) -> str:
    if PLACEHOLDER.search(match.group(2)):
        return match.group(0)
    return f"{match.group(1)}{marker(ENV_CREDENTIAL_RULE)}"


def text(value: str) -> str:

    if not value:
        return value
    value = DUMP_PATTERN.sub(marker(ENVIRONMENT_DUMP_RULE), value)
    value = CREDENTIAL_PATTERN.sub(_credential, value)
    for rule, pattern in SECRET_RULES:
        value = pattern.sub(_secret(rule), value)
    for rule, pattern in (*MACHINE_PATH_RULES, ABSOLUTE_PATH_RULE):
        value = pattern.sub(marker(rule), value)
    return value


def event(value: object) -> object:

    if isinstance(value, str):
        return text(value)
    if isinstance(value, dict):
        return {key: event(item) for key, item in value.items()}
    if isinstance(value, list):
        return [event(item) for item in value]
    return value
