r"""Block commits made with an unconfigured or auto-derived git identity.

Installed as a pre-commit hook via pre-commit. It refuses a commit when the
committer identity is missing or looks like git's hostname fallback (for example
``user@laptop.local``), which silently pollutes history with a machine address —
the exact failure this repo hit when a global ``user.email`` was left unset.

The check is intentionally generic and carries NO project-specific identities, so
it is safe to distribute: it only verifies that ``user.name``/``user.email`` are
explicitly configured and not an obvious auto-generated value. Configure the real
per-repo/per-host identity yourself (``git config --local user.email ...`` or a
conditional include — see the ``tool-git`` skill); this hook guards against the
*absence* of that configuration, not the value.

Optional strict mode: set ``basicly.identityAllowEmail`` to a regular expression
(``git config basicly.identityAllowEmail '@example\.com$'``) and the committer
email must match it — useful to keep a repo's commits on a company/personal domain.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
from pathlib import Path

# Emails git fabricates from the hostname when identity is unset end in these
# machine-local suffixes (e.g. ``visicni@at-work.local``, ``user@host.(none)``).
FALLBACK_EMAIL_PATTERN = re.compile(r"\.(local|lan|localdomain)$|\.?\(none\)$", re.IGNORECASE)


def git_config(key: str, repo_root: Path) -> str:
    """Return the trimmed value of a git config key, or '' if unset."""
    result = subprocess.run(
        ["git", "config", key],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )  # nosec
    return result.stdout.strip()


def check_identity(name: str, email: str, allow_email: str = "") -> tuple[bool, str]:
    """Validate a git identity. Return (ok, message); ok False blocks the commit."""
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
    """Entry point for the identity-guard pre-commit hook."""
    repo_root = Path.cwd()
    name = git_config("user.name", repo_root)
    email = git_config("user.email", repo_root)
    allow_email = git_config("basicly.identityAllowEmail", repo_root)

    ok, message = check_identity(name, email, allow_email)
    if ok:
        print(message)
        return 0

    print(f"ERROR: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
