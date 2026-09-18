from __future__ import annotations

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


def main() -> int:
    repo_root = Path.cwd()
    name = git_config("user.name", repo_root)
    email = git_config("user.email", repo_root)
    allow_email = git_config("basicly.identityAllowEmail", repo_root)

    ok, message = check_identity(name, email, allow_email)
    if not ok:
        print(f"ERROR: {message}", file=sys.stderr)
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
