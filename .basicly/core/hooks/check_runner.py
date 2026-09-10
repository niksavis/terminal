"""Config-driven check runner shared by the pre-commit and pre-push hooks.

Reads ``[[verify.checks]]`` from ``basicly.toml`` and the ``basicly.d`` fragments
beside it, and runs the checks declared for a given mode, so the shipped hooks gate
exactly what each consumer repo configures — a repo with no checks passes with a note
instead of failing on a stack it doesn't have. Standalone: stdlib only, no basicly
import, usable from pre-commit, lefthook, or a bare git hook.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import time
import tomllib
from pathlib import Path, PurePosixPath

CONFIG_FILE = "basicly.toml"

# Per-lane drop-in fragments, whose checks are appended to the config's own. The same set
# `basicly.config` assembles, so a check a lane declared in its own fragment gates the commit
# as well as `basicly verify` (basicly-ef7t; `basicly.d/README.md` is the convention).
FRAGMENT_DIR = "basicly.d"


def project_root() -> Path:
    """Repo root for a hook invocation.

    Git runs hooks with cwd at the top of the working tree, so cwd is
    authoritative; walking up covers direct invocation from a subdirectory.
    Never derived from this file's location — the managed core may be
    relocated via ``basicly.toml [paths]``.
    """
    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _declared_checks(repo_root: Path) -> list[tuple[str, object]]:
    """Every declared check with the file it came from: the config, then the fragments.

    Filename order within the fragment directory, so the assembled set is the same on
    any machine and matches what ``basicly.config`` reads.
    """
    found: list[tuple[str, object]] = []
    for path in (repo_root / CONFIG_FILE, *sorted((repo_root / FRAGMENT_DIR).glob("*.toml"))):
        if not path.exists():
            continue
        section = tomllib.loads(path.read_text(encoding="utf-8")).get("verify", {})
        checks = section.get("checks") if isinstance(section, dict) else None
        if isinstance(checks, list):
            found += [(path.name, entry) for entry in checks]
    return found


def _mode_entries(repo_root: Path, mode: str) -> list[dict]:
    """Return the validated ``[[verify.checks]]`` entries declared for *mode*.

    A missing file or section yields no entries. A malformed check entry is a
    loud error (SystemExit) — a lost gate must never pass unnoticed.
    """
    entries: list[dict] = []
    for source, entry in _declared_checks(repo_root):
        if not isinstance(entry, dict):
            raise SystemExit(f"{source}: [[verify.checks]] entry must be a table")
        name = entry.get("name")
        command = entry.get("command")
        modes = entry.get("modes")
        fix_command = entry.get("fix_command")
        if not (isinstance(name, str) and name.strip()):
            raise SystemExit(f"{source}: a [[verify.checks]] entry is missing 'name'")
        if not (isinstance(command, list) and command and all(isinstance(a, str) for a in command)):
            raise SystemExit(f"{source}: check {name!r} needs a 'command' list of strings")
        if not (isinstance(modes, list) and all(isinstance(m, str) for m in modes)):
            raise SystemExit(f"{source}: check {name!r} needs a 'modes' list of strings")
        if fix_command is not None and not (
            isinstance(fix_command, list)
            and fix_command
            and all(isinstance(a, str) for a in fix_command)
        ):
            raise SystemExit(f"{source}: check {name!r} 'fix_command' must be a list of strings")
        inputs = entry.get("inputs")
        if inputs is not None and not (
            isinstance(inputs, list) and inputs and all(isinstance(g, str) and g for g in inputs)
        ):
            raise SystemExit(f"{source}: check {name!r} 'inputs' must be a list of glob strings")
        if mode in modes:
            entries.append(entry)
    return entries


def load_checks(repo_root: Path, mode: str) -> list[tuple[str, list[str]]]:
    """Return ``(name, command)`` pairs configured for *mode*."""
    return [
        (str(entry["name"]).strip(), list(entry["command"]))
        for entry in _mode_entries(repo_root, mode)
    ]


def load_fixes(repo_root: Path, mode: str) -> list[tuple[str, list[str], str | None]]:
    """Return ``(name, fix_command, staged_suffix)`` for *mode* checks that declare a fix.

    ``fix_command`` is the deterministic, lossless repair for a check (a
    formatter's write mode); ``staged_suffix`` scopes it to the staged files of
    that suffix so a commit-time fix never reformats files the commit doesn't
    touch.
    """
    fixes: list[tuple[str, list[str], str | None]] = []
    for entry in _mode_entries(repo_root, mode):
        fix_command = entry.get("fix_command")
        if not fix_command:
            continue
        suffix = entry.get("staged_suffix")
        fixes.append((
            str(entry["name"]).strip(),
            list(fix_command),
            suffix if isinstance(suffix, str) and suffix else None,
        ))
    return fixes


def load_inputs(repo_root: Path, mode: str) -> dict[str, list[str]]:
    """Return the ``inputs`` globs of each *mode* check that declares any.

    A check absent from the mapping declared none, which means "reads the whole tree":
    the key is how a check opts *into* being skippable, so a consumer that never adds
    one keeps today's behaviour and a new gate is un-skippable until its author says
    what it reads.
    """
    declared: dict[str, list[str]] = {}
    for entry in _mode_entries(repo_root, mode):
        globs = entry.get("inputs")
        if globs:
            declared[str(entry["name"]).strip()] = [str(g) for g in globs]
    return declared


def _git_output(repo_root: Path, *args: str) -> str | None:
    """Stdout of a ``git`` call; None when the call itself failed."""
    try:
        proc = subprocess.run(  # nosec B603 B607
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return None if proc.returncode != 0 else proc.stdout


def _git_lines(repo_root: Path, *args: str) -> list[str] | None:
    """Non-empty output lines of a ``git`` call; None when the call itself failed."""
    out = _git_output(repo_root, *args)
    return None if out is None else [line for line in out.splitlines() if line]


def diff_paths(repo_root: Path) -> list[str] | None:
    """Every path the staged diff touches; None when git could not say.

    No ``--diff-filter``: a deletion or a rename is a change to the file's gates too, and
    the widest answer is the safe one here — this list is what *keeps* a check, so a path
    this misses is a check that gets skipped. ``-z`` for the same reason, because
    ``--name-only`` alone quotes a path holding a non-ASCII byte and a quoted path matches
    no glob anyone would write.
    """
    out = _git_output(repo_root, "diff", "--cached", "--name-only", "-z")
    return None if out is None else [path for path in out.split("\0") if path]


def scoped_skips(repo_root: Path, mode: str) -> dict[str, str]:
    """Return ``name -> reason`` for each *mode* check the staged diff cannot affect.

    The inner loop of a lane runs the gates whose declared inputs its diff touches; the
    landing runs the mode (``full``) that declares no ``inputs`` at all, so a gate skipped
    here is still the thing that has to pass before anything merges. That asymmetry is what
    makes the skip affordable — and it is also why every uncertainty resolves to *running*
    the check: git failing, an empty diff, and a check that declared no inputs all yield no
    skip at all.
    """
    if not (declared := load_inputs(repo_root, mode)):
        return {}
    changed = diff_paths(repo_root)
    if not changed:
        return {}
    skips: dict[str, str] = {}
    for name, globs in declared.items():
        if not any(PurePosixPath(path).full_match(glob) for path in changed for glob in globs):
            skips[name] = f"no staged path matches its inputs ({' '.join(globs)})"
    return skips


def apply_fixes(repo_root: Path, mode: str) -> None:
    """Apply the declared mechanical repairs to the staged files and re-stage them.

    Repairs the classes of failure a script can fix losslessly (formatting), so
    the commit carries the fixed bytes and the check that follows passes without
    anyone hand-running the formatter. Never a verdict: a fixer that cannot run
    is reported and the checks still decide the outcome.

    Only files that were fully staged (no unstaged changes of their own) are
    re-staged — re-adding a partially staged file would silently commit work the
    author left out of the index. Those keep their staged bytes and the check
    reports them as it did before.
    """
    fixes = load_fixes(repo_root, mode)
    if not fixes:
        return

    staged = _git_lines(repo_root, "diff", "--cached", "--name-only", "--diff-filter=ACM")
    dirty_before = _git_lines(repo_root, "diff", "--name-only")
    if staged is None or dirty_before is None:
        print("skipping auto-fix: cannot read the git index", file=sys.stderr)
        return
    if not staged:
        return

    applied = _run_fixers(repo_root, fixes, staged)
    if applied:
        _restage_fixed(repo_root, staged, dirty_before, applied)


def _run_fixers(
    repo_root: Path, fixes: list[tuple[str, list[str], str | None]], staged: list[str]
) -> list[str]:
    """Run each fixer over its staged targets; return the names that ran clean."""
    applied: list[str] = []
    for name, command, suffix in fixes:
        targets = [path for path in staged if path.endswith(suffix)] if suffix else []
        if suffix and not targets:
            continue
        try:
            result = subprocess.run(command + targets, cwd=repo_root, check=False)  # nosec B603
        except OSError as exc:
            print(f"auto-fix {name} could not run: {exc.strerror or exc}", file=sys.stderr)
            continue
        if result.returncode != 0:
            print(f"auto-fix {name} exited {result.returncode}", file=sys.stderr)
            continue
        applied.append(name)
    return applied


def _restage_fixed(
    repo_root: Path, staged: list[str], dirty_before: list[str], applied: list[str]
) -> None:
    """Stage the files a fixer rewrote, excluding any that were already dirty."""
    dirty_after = _git_lines(repo_root, "diff", "--name-only")
    if dirty_after is None:
        print("skipping re-stage: cannot read the git working tree", file=sys.stderr)
        return
    restage = sorted((set(dirty_after) - set(dirty_before)) & set(staged))
    if not restage:
        return
    if _git_lines(repo_root, "add", "--", *restage) is None:
        print(f"auto-fix changed {', '.join(restage)} but re-staging failed", file=sys.stderr)
        return
    print(f"auto-fixed and re-staged ({', '.join(applied)}): {', '.join(restage)}")


def run_checks(repo_root: Path, mode: str, *, scope_to_diff: bool = False) -> int:
    """Run every check configured for *mode*; return a process exit code.

    ``scope_to_diff`` skips the checks whose declared ``inputs`` the staged diff cannot
    reach (:func:`scoped_skips`), naming each one it skips. Off by default, so ``full``
    — the mode a landing and a push run — is every declared check whatever any of them
    says about its inputs.
    """
    checks = load_checks(repo_root, mode)
    if not checks:
        print(f"No verify checks configured for mode '{mode}' in {CONFIG_FILE}; nothing to gate.")
        return 0

    skips = scoped_skips(repo_root, mode) if scope_to_diff else {}
    total_start = time.perf_counter()
    failed: list[str] = []
    for name, command in checks:
        if name in skips:
            print(f"==> {name} SKIPPED: {skips[name]}")
            continue
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
    ran = len(checks) - len(skips)
    tail = f" ({len(skips)} skipped: {', '.join(sorted(skips))})" if skips else ""
    if failed:
        print(
            f"checks failed: {ran - len(failed)}/{ran} passed in {total_elapsed:.2f}s "
            f"(failed: {', '.join(failed)}){tail}",
            file=sys.stderr,
        )
        return 1
    print(f"checks passed: {ran}/{ran} in {total_elapsed:.2f}s{tail}")
    return 0
