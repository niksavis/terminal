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

An opt-in per-agent bot identity (``basicly-smzg``) overrides the recorded
author/committer via the ``GIT_AUTHOR_*``/``GIT_COMMITTER_*`` environment without
touching config, so the guard also validates the *effective* identity git will
actually stamp (via ``git var``), not just the config value — otherwise a bot
could commit under an email the allow-email pattern forbids.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
from pathlib import Path

# Emails git fabricates from the hostname when identity is unset end in these
# machine-local suffixes (e.g. ``visicni@at-work.local``, ``user@host.(none)``).
FALLBACK_EMAIL_PATTERN = re.compile(r"\.(local|lan|localdomain)$|\.?\(none\)$", re.IGNORECASE)

# ``git var GIT_{AUTHOR,COMMITTER}_IDENT`` renders as ``Name <email> unixtime +tz``.
IDENT_PATTERN = re.compile(r"^(?P<name>.*) <(?P<email>[^>]*)> \d+ [-+]\d{4}$")


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


def effective_identity(role: str, repo_root: Path) -> tuple[str, str]:
    """The name/email git will actually stamp for *role* (``AUTHOR``/``COMMITTER``).

    ``git var GIT_<role>_IDENT`` resolves the effective identity from the
    ``GIT_<role>_NAME``/``GIT_<role>_EMAIL`` environment first (an opt-in bot
    identity, basicly-smzg), then config — so the guard validates what history
    records, not only what config says. Returns ``("", "")`` when the output
    cannot be parsed; the caller treats that as "no override to check" so a parse
    miss never false-blocks a commit the config check already cleared.
    """
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
    if not ok:
        print(f"ERROR: {message}", file=sys.stderr)
        return 1
    print(message)

    # An opt-in bot identity (basicly-smzg) overrides the recorded author/committer
    # via GIT_AUTHOR_*/GIT_COMMITTER_* env without touching config. Validate the
    # effective identity git will actually stamp so the allow-email gate binds the
    # bot too. When it equals config (no override) or cannot be parsed, skip it —
    # the config check above already covered the base identity.
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
