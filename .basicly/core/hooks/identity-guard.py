from __future__ import annotations

import json
import re
import subprocess  # nosec B404
import sys
from pathlib import Path

FALLBACK_EMAIL_PATTERN = re.compile(r"\.(local|lan|localdomain)$|\.?\(none\)$", re.IGNORECASE)

IDENT_PATTERN = re.compile(r"^(?P<name>.*) <(?P<email>[^>]*)> \d+ [-+]\d{4}$")


def git_config(key: str, repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "config", key],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )  # nosec
    return result.stdout.strip()


def effective_identity(role: str, repo_root: Path) -> tuple[str, str]:

    result = subprocess.run(
        ["git", "var", f"GIT_{role}_IDENT"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )  # nosec
    match = IDENT_PATTERN.match(result.stdout.strip())
    if not match:
        return "", ""
    return match.group("name").strip(), match.group("email").strip()


def check_identity(name: str, email: str, allow_email: str = "") -> tuple[bool, str]:
    if not email:
        return False, (
            "no git user.email is configured — git would fall back to a hostname "
            "address. Set one with: git config --local user.email <you@example.com>"
        )
    if FALLBACK_EMAIL_PATTERN.search(email):
        return False, (
            f"git user.email '{email}' looks auto-generated from the hostname. Set a "
            "real address with: git config --local user.email <you@example.com>"
        )
    if not name:
        return False, (
            "no git user.name is configured. "
            "Set one with: git config --local user.name '<Your Name>'"
        )
    if allow_email and not re.search(allow_email, email):
        return False, (
            f"git user.email '{email}' does not match the required pattern "
            f"basicly.identityAllowEmail='{allow_email}'."
        )
    return True, f"git identity OK: {name} <{email}>"


LEDGER_PREFIX = ".basicly/ledger/"
HOLDER_FIELD = "assignee"
MIN_NAME_CHARS = 3


def added_lines(repo_root: Path) -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )  # nosec
    found, path = [], ""
    for line in result.stdout.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and path:
            found.append((path, line[1:]))
    return found


def _forms(name: str) -> tuple[str, ...]:
    return (name, json.dumps(name)[1:-1])


def _only_the_holder(line: str, name: str, holder: str) -> bool:
    try:
        event = json.loads(line)
    except ValueError:
        return False
    payload = event.get("payload") if isinstance(event, dict) else None
    if not isinstance(payload, dict) or payload.get("name") != HOLDER_FIELD:
        return False
    if payload.get("value") != holder:
        return False
    rest = json.dumps({**event, "payload": {**payload, "value": ""}})
    return not any(form in rest for form in _forms(name))


def name_findings(lines: list[tuple[str, str]], name: str, holder: str) -> list[str]:
    if len(name) < MIN_NAME_CHARS:
        return []
    findings = []
    for path, line in lines:
        if not any(form in line for form in _forms(name)):
            continue
        if path.startswith(LEDGER_PREFIX) and _only_the_holder(line, name, holder):
            continue
        findings.append(path)
    return sorted(set(findings))


def main() -> int:
    repo_root = Path.cwd()
    name = git_config("user.name", repo_root)
    email = git_config("user.email", repo_root)
    allow_email = git_config("basicly.identityAllowEmail", repo_root)

    ok, message = check_identity(name, email, allow_email)
    if not ok:
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    holder = git_config("basicly.holder", repo_root) or name
    if found := name_findings(added_lines(repo_root), name, holder):
        print(
            f"ERROR: the commit adds your git user.name to {', '.join(found)}. Commit no user "
            "name; the tracker holder field is the one exception, and "
            "`git config basicly.holder <name>` chooses what it records",
            file=sys.stderr,
        )
        return 1
    print(message)

    for role in ("AUTHOR", "COMMITTER"):
        eff_name, eff_email = effective_identity(role, repo_root)
        if not eff_email or (eff_name, eff_email) == (name, email):
            continue
        ok, message = check_identity(eff_name, eff_email, allow_email)
        if not ok:
            print(f"ERROR: effective {role.lower()} identity: {message}", file=sys.stderr)
            return 1
        print(f"effective {role.lower()} identity OK: {eff_name} <{eff_email}>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
