from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path

ALLOW_PRAGMA = "pragma: allow internal"

CONFIG_FILE = "basicly.local.toml"


def load_rules(repo_root: Path) -> list[tuple[str, str]]:

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
    if ALLOW_PRAGMA in text:
        return None
    lowered = text.lower()
    return next((name for name, token in rules if token in lowered), None)


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
