from __future__ import annotations

import importlib.util
import json
import os
import subprocess  # nosec B404
import sys
import time
import tomllib
from pathlib import Path, PurePosixPath
from typing import Any

CONFIG_FILE = "basicly.toml"

FRAGMENT_DIR = "basicly.d"

VENV_CONFIG = Path(".venv") / "pyvenv.cfg"


def interpreter_home(repo_root: Path) -> Path:

    try:
        lines = (repo_root / VENV_CONFIG).read_text(encoding="utf-8").splitlines()
    except OSError:
        return Path(sys.base_prefix)
    for line in lines:
        key, _, value = line.partition("=")
        if key.strip() == "home" and value.strip():
            return Path(value.strip())
    return Path(sys.base_prefix)


def interpreter_target(home: Path) -> str | None:

    try:
        return home.resolve(strict=True).as_posix()
    except OSError:
        return None


def interpreter_swap_notice(home: Path, before: str | None) -> str | None:

    after = interpreter_target(home)
    if after == before:
        return None
    return (
        f"the Python behind this run changed while it ran: {before or 'missing'} -> "
        f"{after or 'missing'} (through {home}). A `uv python upgrade` or "
        "`uv python install --upgrade` moves every uv venv to the new patch release, so a "
        "check that ran during the swap fails for that reason, not for this change. "
        "Run the checks again."
    )


def project_root() -> Path:

    cwd = Path.cwd()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _documents(repo_root: Path) -> list[tuple[str, dict]]:
    return [
        (path.name, tomllib.loads(path.read_text(encoding="utf-8")))
        for path in (
            repo_root / CONFIG_FILE,
            *sorted((repo_root / FRAGMENT_DIR).glob("*.toml")),
            repo_root / "basicly.local.toml",
        )
        if path.exists()
    ]


def _declared_checks(repo_root: Path) -> list[tuple[str, object]]:

    found: list[tuple[str, object]] = []
    for name, document in _documents(repo_root):
        section = document.get("verify", {})
        checks = section.get("checks") if isinstance(section, dict) else None
        if isinstance(checks, list):
            additions = [(name, entry) for entry in checks]
            found = additions if name == "basicly.local.toml" else [*found, *additions]
    return found


def _mode_entries(repo_root: Path, mode: str | None) -> list[dict]:

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
        if mode is None or mode in modes:
            entries.append(entry)
    return entries


def resolve_command(command: list[str], repo_root: Path) -> list[str]:
    source = Path(__file__).with_name("command_paths.py")
    spec = importlib.util.spec_from_file_location("basicly_hook_command_paths", source)
    if spec is None or spec.loader is None:
        raise ValueError("check command path runtime is missing; run basicly install")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.resolve_command(command, repo_root)


def load_checks(repo_root: Path, mode: str) -> list[tuple[str, list[str]]]:
    return [
        (str(entry["name"]).strip(), list(entry["command"]))
        for entry in _mode_entries(repo_root, mode)
    ]


def load_fixes(repo_root: Path, mode: str) -> list[tuple[str, list[str], str | None]]:

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

    declared: dict[str, list[str]] = {}
    for entry in _mode_entries(repo_root, mode):
        globs = entry.get("inputs")
        if globs:
            declared[str(entry["name"]).strip()] = [str(g) for g in globs]
    return declared


def _affected_module() -> Any:
    source = Path(__file__).with_name("affected_checks.py")
    spec = importlib.util.spec_from_file_location("basicly_hook_affected_checks", source)
    if spec is None or spec.loader is None:
        raise ValueError("affected check runtime is missing; run basicly install")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _selection(repo_root: Path, checks: list[tuple[str, list[str]]]) -> dict | None:
    section = None
    for _, document in _documents(repo_root):
        verify = document.get("verify", {})
        if isinstance(verify, dict) and "affected" in verify:
            section = verify["affected"]
    if section is None:
        return None
    module = _affected_module()
    names = [entry["name"].strip() for entry in _mode_entries(repo_root, None)]
    provider = module.parse_provider(section, names)
    return module.select(
        repo_root,
        provider,
        [name for name, _ in checks],
        snapshot_tree=os.environ.get("BASICLY_SNAPSHOT_TREE"),
    )


def _record_selection(repo_root: Path, plan: dict, outcomes: list[dict]) -> None:
    path = repo_root / ".basicly/usage/affected-run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps({"selection": plan, "checks": outcomes}, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _git_output(repo_root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(  # nosec B603 B607
            ["git", *args],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return None
    return None if proc.returncode != 0 else proc.stdout


def _git_lines(repo_root: Path, *args: str) -> list[str] | None:
    out = _git_output(repo_root, *args)
    return None if out is None else [line for line in out.splitlines() if line]


def diff_paths(repo_root: Path) -> list[str] | None:

    out = _git_output(repo_root, "diff", "--cached", "--name-only", "-z")
    return None if out is None else [path for path in out.split("\0") if path]


def scoped_skips(repo_root: Path, mode: str) -> dict[str, str]:

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
        _restage_fixed(repo_root, dirty_before, applied)


def _run_fixers(
    repo_root: Path, fixes: list[tuple[str, list[str], str | None]], staged: list[str]
) -> list[str]:
    applied: list[str] = []
    for name, command, suffix in fixes:
        targets = [path for path in staged if path.endswith(suffix)] if suffix else []
        if suffix and not targets:
            continue
        try:
            result = subprocess.run(
                resolve_command(command, repo_root) + targets, cwd=repo_root, check=False
            )  # nosec B603
        except OSError as exc:
            print(f"auto-fix {name} could not run: {exc.strerror or exc}", file=sys.stderr)
            continue
        if result.returncode != 0:
            print(f"auto-fix {name} exited {result.returncode}", file=sys.stderr)
            continue
        applied.append(name)
    return applied


def _restage_fixed(repo_root: Path, dirty_before: list[str], applied: list[str]) -> None:
    dirty_after = _git_lines(repo_root, "diff", "--name-only")
    if dirty_after is None:
        print("skipping re-stage: cannot read the git working tree", file=sys.stderr)
        return
    restage = sorted(set(dirty_after) - set(dirty_before))
    if not restage:
        return
    if _git_lines(repo_root, "add", "--", *restage) is None:
        print(f"auto-fix changed {', '.join(restage)} but re-staging failed", file=sys.stderr)
        return
    print(f"auto-fixed and re-staged ({', '.join(applied)}): {', '.join(restage)}")


def _planned_skips(
    repo_root: Path, mode: str, checks: list[tuple[str, list[str]]], scope_to_diff: bool
) -> tuple[dict | None, dict[str, str]]:
    selection = _selection(repo_root, checks) if scope_to_diff else None
    if selection is not None:
        skips = {
            name: selection["reasons"][name]
            for name, _ in checks
            if name not in selection["selected"]
        }
        if selection["fallback"]:
            print(f"affected checks: {selection['fallback']}")
    else:
        skips = scoped_skips(repo_root, mode) if scope_to_diff else {}
    return selection, skips


def run_checks(repo_root: Path, mode: str, *, scope_to_diff: bool = False) -> int:

    fail_fast = load_fail_fast(repo_root)
    checks = load_checks(repo_root, mode)
    if not checks:
        print(f"No verify checks configured for mode '{mode}' in {CONFIG_FILE}; nothing to gate.")
        return 0
    selection, skips = _planned_skips(repo_root, mode, checks, scope_to_diff)
    if selection and selection["invalid_snapshot"]:
        print(f"affected checks failed: {selection['fallback']}", file=sys.stderr)
        _record_selection(repo_root, selection, [])
        return 1
    home = interpreter_home(repo_root)
    interpreter_before = interpreter_target(home)
    total_start = time.perf_counter()
    failed: list[str] = []
    outcomes: list[dict] = []
    for name, command in checks:
        if name in skips:
            print(f"==> {name} SKIPPED: {skips[name]}", flush=True)
            outcomes.append({"name": name, "disposition": "not-selected", "reason": skips[name]})
            continue
        if fail_fast and failed:
            outcomes.append(_blocked_outcome(name, failed[0]))
            continue
        print(f"==> {name}", flush=True)
        start = time.perf_counter()
        try:
            result = subprocess.run(resolve_command(command, repo_root), cwd=repo_root, check=False)  # nosec B603
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
        outcomes.append({
            "name": name,
            "disposition": "executed",
            "returncode": code,
            "duration_s": elapsed,
        })
        if code != 0:
            failed.append(name)
            print(f"FAILED: {name} ({elapsed:.2f}s)", file=sys.stderr)

    total_elapsed = time.perf_counter() - total_start
    if selection is not None:
        _record_selection(repo_root, selection, outcomes)
    blocked = [r["name"] for r in outcomes if r["disposition"] == "not-run"]
    ran = len(checks) - len(skips) - len(blocked)
    tail = f" ({len(skips)} skipped: {', '.join(sorted(skips))})" if skips else ""
    tail += f" ({len(blocked)} not run: {', '.join(blocked)})" if blocked else ""
    if failed:
        print(
            f"checks failed: {ran - len(failed)}/{ran} passed in {total_elapsed:.2f}s "
            f"(failed: {', '.join(failed)}){tail}",
            file=sys.stderr,
        )
        notice = interpreter_swap_notice(home, interpreter_before)
        if notice:
            print(f"checks: {notice}", file=sys.stderr)
        return 1
    print(f"checks passed: {ran}/{ran} in {total_elapsed:.2f}s{tail}")
    return 0


def load_fail_fast(repo_root: Path) -> bool:
    return _boolean_option(repo_root, "fail_fast")


def load_cache(repo_root: Path) -> bool:
    return _boolean_option(repo_root, "cache")


def _boolean_option(repo_root: Path, name: str) -> bool:
    enabled = False
    for _, document in _documents(repo_root):
        section = document.get("verify", {})
        if isinstance(section, dict) and name in section:
            enabled = section[name]
    if not isinstance(enabled, bool):
        raise SystemExit(f"verify.{name} must be true or false")
    return enabled


def _blocked_outcome(name: str, failed: str) -> dict:
    reason = f"not run after failed check {failed}"
    print(f"==> {name} NOT RUN: {reason}", flush=True)
    return {"name": name, "disposition": "not-run", "reason": reason}
