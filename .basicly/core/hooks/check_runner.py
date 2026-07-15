"""Config-driven check runner shared by the pre-commit and pre-push hooks.

Reads ``[[verify.checks]]`` from ``basicly.toml`` and runs the checks declared
for a given mode, so the shipped hooks gate exactly what each consumer repo
configures — a repo with no checks passes with a note instead of failing on a
stack it doesn't have. Standalone: stdlib only, no basicly import, usable from
pre-commit, lefthook, or a bare git hook.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import time
import tomllib
from pathlib import Path

CONFIG_FILE = "basicly.toml"


def load_checks(repo_root: Path, mode: str) -> list[tuple[str, list[str]]]:
    """Return ``(name, command)`` pairs configured for *mode*.

    A missing file or section yields no checks. A malformed check entry is a
    loud error (SystemExit) — a lost gate must never pass unnoticed.
    """
    config_path = repo_root / CONFIG_FILE
    if not config_path.exists():
        return []

    data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    section = data.get("verify", {})
    raw_checks = section.get("checks") if isinstance(section, dict) else None
    if not isinstance(raw_checks, list):
        return []

    checks: list[tuple[str, list[str]]] = []
    for entry in raw_checks:
        if not isinstance(entry, dict):
            raise SystemExit(f"{CONFIG_FILE}: [[verify.checks]] entry must be a table")
        name = entry.get("name")
        command = entry.get("command")
        modes = entry.get("modes")
        if not (isinstance(name, str) and name.strip()):
            raise SystemExit(f"{CONFIG_FILE}: a [[verify.checks]] entry is missing 'name'")
        if not (isinstance(command, list) and command and all(isinstance(a, str) for a in command)):
            raise SystemExit(f"{CONFIG_FILE}: check {name!r} needs a 'command' list of strings")
        if not (isinstance(modes, list) and all(isinstance(m, str) for m in modes)):
            raise SystemExit(f"{CONFIG_FILE}: check {name!r} needs a 'modes' list of strings")
        if mode in modes:
            checks.append((name.strip(), list(command)))
    return checks


def run_checks(repo_root: Path, mode: str) -> int:
    """Run every check configured for *mode*; return a process exit code."""
    checks = load_checks(repo_root, mode)
    if not checks:
        print(f"No verify checks configured for mode '{mode}' in {CONFIG_FILE}; nothing to gate.")
        return 0

    total_start = time.perf_counter()
    failed: list[str] = []
    for name, command in checks:
        print(f"==> {name}")
        start = time.perf_counter()
        try:
            result = subprocess.run(command, cwd=repo_root, check=False)  # nosec B603
            code = result.returncode
        except FileNotFoundError:
            print(
                f"FAILED: {name} — command not found: {command[0]} "
                f"(install it or edit [[verify.checks]] in {CONFIG_FILE})",
                file=sys.stderr,
            )
            code = 127
        except OSError as exc:
            print(
                f"FAILED: {name} — cannot run {command[0]} ({exc.strerror or exc})",
                file=sys.stderr,
            )
            code = 126
        elapsed = time.perf_counter() - start
        if code != 0:
            failed.append(name)
            print(f"FAILED: {name} ({elapsed:.2f}s)", file=sys.stderr)

    total_elapsed = time.perf_counter() - total_start
    passed_count = len(checks) - len(failed)
    if failed:
        print(
            f"checks failed: {passed_count}/{len(checks)} passed in {total_elapsed:.2f}s "
            f"(failed: {', '.join(failed)})",
            file=sys.stderr,
        )
        return 1
    print(f"checks passed: {len(checks)}/{len(checks)} in {total_elapsed:.2f}s")
    return 0
