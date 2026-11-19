from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path

ALLOWLIST_PRAGMA = "pragma: allowlist secret"
PRECOMMIT_CONFIG = ".pre-commit-config.yaml"
ALLOW_FILE = ".secret-scan-allow.toml"

_GENERIC_RULE = "generic-secret-assignment"
MIN_ALLOWED = 12
_QUOTED = re.compile(r"['\"]([^'\"]*)['\"]$")

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


def rule_hit(text: str, *, generic: bool = True) -> str | None:
    if ALLOWLIST_PRAGMA in text:
        return None
    for name, pattern in _RULES:
        if pattern.search(text):
            if name == _GENERIC_RULE and (not generic or _PLACEHOLDER.search(text)):
                continue
            return name
    return None


def precommit_exclude(config: str) -> str | None:
    lines = config.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"exclude:\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match.group(1)
        if value[:1] in ("|", ">"):
            block = []
            for follow in lines[index + 1 :]:
                if follow.strip() and not follow[:1].isspace():
                    break
                block.append(follow.strip())
            return ("\n" if value[0] == "|" else " ").join(part for part in block if part)
        if len(value) > 1 and value[0] == value[-1] == "'":
            return value[1:-1].replace("''", "'")
        if len(value) > 1 and value[0] == value[-1] == '"':
            return re.sub(r"\\(.)", r"\1", value[1:-1])
        return re.split(r"\s+#", value)[0] or None
    return None


def excluded_paths() -> re.Pattern[str] | None:
    if "BASICLY_SECRET_EXCLUDE" in os.environ:
        source = os.environ["BASICLY_SECRET_EXCLUDE"]
        return re.compile(source) if source else None
    config = Path(PRECOMMIT_CONFIG)
    if not config.is_file():
        return None
    source = precommit_exclude(config.read_text(encoding="utf-8"))
    return re.compile(source) if source else None


def allowable(text: str) -> bool:
    generic = dict(_RULES)[_GENERIC_RULE]
    for match in generic.finditer(text):
        quoted = _QUOTED.search(match.group(0))
        if quoted is None or len(quoted.group(1)) < MIN_ALLOWED:
            return False
    return True


def line_hash(text: str) -> str:
    return hashlib.sha256(text.rstrip("\r").encode("utf-8")).hexdigest()


def _staged_text(path: str) -> str | None:
    proc = subprocess.run(  # nosec B603 B607
        ["git", "show", f":{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _entry_error(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return "an [[allow]] entry is not a table"
    if entry.get("rule") != _GENERIC_RULE:
        return f"rule must be {_GENERIC_RULE!r}; a key-format rule is never allowed"
    if not isinstance(entry.get("path"), str) or not entry["path"]:
        return "path must name the file that holds the line"
    if not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("line_sha256", ""))):
        return "line_sha256 must be the 64-character hash that the refusal printed"
    if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
        return "reason must say why the line holds no secret"
    return None


def allowed_lines() -> tuple[set[tuple[str, str]], list[str]]:

    source = _staged_text(ALLOW_FILE)
    if source is None:
        return set(), []
    try:
        entries = tomllib.loads(source).get("allow", [])
    except tomllib.TOMLDecodeError as err:
        return set(), [f"allow-file-invalid: {ALLOW_FILE} is not valid TOML ({err})"]
    if not isinstance(entries, list):
        return set(), [f"allow-file-invalid: {ALLOW_FILE} must hold [[allow]] entries"]
    allowed: set[tuple[str, str]] = set()
    errors: list[str] = []
    for number, entry in enumerate(entries, start=1):
        if (problem := _entry_error(entry)) is not None:
            errors.append(f"allow-entry-invalid: {ALLOW_FILE} entry {number}: {problem}")
            continue
        path, digest = entry["path"], entry["line_sha256"]
        staged = _staged_text(path)
        if staged is None or digest not in {line_hash(line) for line in staged.splitlines()}:
            errors.append(
                f"allow-entry-stale: {ALLOW_FILE} entry {number} ({path} sha256:{digest}) "
                "matches no line in the staged file; remove the entry"
            )
            continue
        allowed.add((path, digest))
    return allowed, errors


def _allow_entry(path: str, digest: str) -> str:
    return (
        f"[[allow]]\nrule = {json.dumps(_GENERIC_RULE)}\npath = {json.dumps(path)}\n"
        f'line_sha256 = "{digest}"\nreason = ""'
    )


def staged_added_lines() -> list[tuple[str, int, str]]:

    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        encoding="utf-8",
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


def _report(findings: list[tuple[str, int, str, str]]) -> None:
    print("secret-scan: possible secret(s) in staged content — commit blocked.", file=sys.stderr)
    for path, lineno, rule, digest in findings:
        shown = f" sha256:{digest}" if rule == _GENERIC_RULE and digest else ""
        if rule == _GENERIC_RULE and not digest:
            shown = f" (a value under {MIN_ALLOWED} characters cannot be allowed by an entry)"
        print(f"  {path}:{lineno}: {rule}{shown}", file=sys.stderr)
    print(
        f"Remove the secret, or if it is a false positive add a "
        f"'{ALLOWLIST_PRAGMA}' comment on the line.",
        file=sys.stderr,
    )
    generic = [
        (path, digest) for path, _, rule, digest in findings if rule == _GENERIC_RULE and digest
    ]
    if not generic:
        return
    print(
        f"A person must read each {_GENERIC_RULE} line above first. Only when it holds no "
        f"secret, add its entry to {ALLOW_FILE}, write the reason, and stage that file:",
        file=sys.stderr,
    )
    for path, digest in dict.fromkeys(generic):
        print(_allow_entry(path, digest), file=sys.stderr)


def main() -> int:
    try:
        excluded = excluded_paths()
    except re.error as err:
        print(
            f"secret-scan: the top-level exclude in {PRECOMMIT_CONFIG} is not a valid regex "
            f"({err}), so nothing was scanned; fix that exclude and commit again.",
            file=sys.stderr,
        )
        return 1
    allowed, errors = allowed_lines()
    for error in errors:
        print(f"secret-scan: {error}", file=sys.stderr)
    findings = [
        (path, lineno, rule, line_hash(text) if rule != _GENERIC_RULE or allowable(text) else "")
        for path, lineno, text in staged_added_lines()
        if (rule := rule_hit(text, generic=not (excluded and excluded.search(path))))
    ]
    findings = [
        finding
        for finding in findings
        if finding[2] != _GENERIC_RULE or (finding[0], finding[3]) not in allowed
    ]
    if findings:
        _report(findings)
    return 1 if findings or errors else 0


if __name__ == "__main__":
    sys.exit(main())
