"""Block a commit that stages an internal-only identifier (basicly-0n3d).

A public repo publishes everything it commits. Internal identifiers — a company
domain, an internal git host, a machine or corporate username, the name of a
private sibling repo — are legitimate content nowhere in a published tree, but
nothing deterministic kept them out until this gate: they arrive through test
fixtures, docstring examples, and machine-written tracker records, and each one
reads as ordinary text to a reviewer who does not already know it is internal.

Design choices, and the reasoning that forced each one:

- **The denylist is never committed.** A gate that hard-codes the strings it
  suppresses publishes them itself — into this repo *and*, because catalog hooks
  are copied by ``basicly install``, into every consumer. So the tokens live in
  ``basicly.local.toml``, which is gitignored as the machine-local half of the
  config surface, and this script ships with no internal string in it at all.
- **Only the rule name is printed, never the token.** Pre-commit also runs in CI,
  whose logs are public on a public repo, so echoing the matched text would leak
  it at exactly the moment the gate fires. Each rule is ``name`` + ``token``; the
  report says ``corp-domain``, and the developer who owns the config knows what
  that means. Same shape as ``secret-scan``, for the same reason.
- **Inert without configuration.** No config file, no ``[[privacy.denied]]``
  table, or a file that will not parse — the gate returns 0. A consumer who never
  configures it is never blocked by it, which is what makes it safe to ship
  enabled.
- **Added lines only.** It scans ``git diff --cached``, so a pre-existing hit
  further down a file never blocks an unrelated commit, and history is out of
  scope (a rewrite cannot un-publish what is already public anyway). This is the
  opposite call from ``tracker-path-scan``, which scans whole staged files
  because a machine-written log is rewritten in bulk — here, any line the store
  rewrites *is* an added line, so the narrower scan loses nothing.
- **Reviewed exceptions are silenced inline** with a ``pragma: allow internal``
  marker on the line. A legitimate external citation can contain a denied
  substring — a public URL whose slug happens to match a private repo name is the
  case that prompted this — and a gate with no escape hatch gets disabled.
- **Case-insensitive substring match, not regex.** The tokens are proper nouns,
  not shapes; a substring test cannot be written wrong, and a config file is a
  bad place to debug a regex.
- **stdlib only**, by the hooks convention — no dependency ships to consumers.

Configure in ``basicly.local.toml`` (gitignored)::

    [[privacy.denied]]
    name = "corp-domain"
    token = "internal.example"

    [[privacy.denied]]
    name = "machine-user"
    token = "example-user"
"""

from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path

# Inline marker that silences a flagged line (a reviewed false positive).
ALLOW_PRAGMA = "pragma: allow internal"

# Machine-local config holding the denylist. Gitignored by design — see the
# module docstring for why the tokens must not live in this script.
CONFIG_FILE = "basicly.local.toml"


def load_rules(repo_root: Path) -> list[tuple[str, str]]:
    """(rule name, lowercased token) for each configured rule; [] when unconfigured.

    Tolerant by design: a missing file, unreadable bytes, invalid TOML, or a
    malformed entry yields no rules rather than an error. This runs on the commit
    path, and a gate that cannot read its own optional config must not be the
    reason a commit fails.
    """
    try:
        data = tomllib.loads((repo_root / CONFIG_FILE).read_text(encoding="utf-8"))
    except OSError, tomllib.TOMLDecodeError, UnicodeDecodeError:
        return []
    entries = data.get("privacy", {}).get("denied", [])
    if not isinstance(entries, list):
        return []
    rules: list[tuple[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name, token = entry.get("name"), entry.get("token")
        if isinstance(name, str) and isinstance(token, str) and name and token:
            rules.append((name, token.lower()))
    return rules


def rule_hit(text: str, rules: list[tuple[str, str]]) -> str | None:
    """The name of the first rule *text* trips, or None (allowlisted/clean)."""
    if ALLOW_PRAGMA in text:
        return None
    lowered = text.lower()
    return next((name for name, token in rules if token in lowered), None)


def staged_added_lines() -> list[tuple[str, int, str]]:
    """(path, new-file line number, text) for every added line in the staged diff.

    Parses ``git diff --cached --unified=0``: ``+++ b/<path>`` sets the file, each
    ``@@ … +start …`` hunk resets the new-file line counter, and ``+`` lines are
    the added content (``-`` lines never advance the new-file counter).
    """
    proc = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=False,
    )
    added: list[tuple[str, int, str]] = []
    path: str | None = None
    lineno = 0
    in_hunk = False  # once a hunk starts, `+++ ` is added content, not a header
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
    """Fail the commit when a staged added line carries a configured internal token."""
    rules = load_rules(Path.cwd())
    if not rules:
        return 0
    findings = [
        (path, lineno, rule)
        for path, lineno, text in staged_added_lines()
        if (rule := rule_hit(text, rules))
    ]
    if not findings:
        return 0
    print(
        "internal-info-scan: internal identifier(s) in staged content — commit blocked.",
        file=sys.stderr,
    )
    for path, lineno, rule in findings[:20]:
        print(f"  {path}:{lineno}: {rule}", file=sys.stderr)
    if len(findings) > 20:
        print(f"  … and {len(findings) - 20} more", file=sys.stderr)
    print(
        f"Committed content is published. Replace the identifier with a generic "
        f"placeholder, or if this one is a reviewed false positive (a public URL "
        f"that happens to contain it, say) add a '{ALLOW_PRAGMA}' comment on the line.\n"
        f"The rule names come from [[privacy.denied]] in {CONFIG_FILE}.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
