from __future__ import annotations

import argparse
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from terminal_setup import harness  # noqa: E402

BUNDLE = ROOT / "terminal_setup" / "templates" / "cli-tools"
SKILL = "cli-tools"
REFRESH = "uv run python .scripts/bundle_cli_tools_skill.py"
INSTALL_STATE = ".basicly/state/install.json"
REMOVES_FILES = 3


def in_ci(environ: dict[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get("CI", "")
    return value.strip().lower() not in {"", "0", "false", "no"}


def render(spec: str, home: Path, *, offline: bool) -> subprocess.CompletedProcess[str]:
    command = ["uv", "tool", "run", *(["--offline"] if offline else []), "--from", spec]
    return subprocess.run(  # nosec B603
        [*command, "basicly", "skills-user", "--home", str(home), SKILL],
        capture_output=True,
        text=True,
        check=False,
    )


def tree(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8").replace("\r\n", "\n")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def differences(bundled: dict[str, str], pinned: dict[str, str]) -> list[str]:
    lines = [f"missing from the bundle: {name}" for name in sorted(pinned.keys() - bundled.keys())]
    lines += [f"not in the pinned skill: {name}" for name in sorted(bundled.keys() - pinned.keys())]
    lines += [
        f"differs from the pinned skill: {name}"
        for name in sorted(bundled.keys() & pinned.keys())
        if bundled[name] != pinned[name]
    ]
    return lines


def write_bundle(files: dict[str, str], bundle: Path = BUNDLE) -> None:
    if bundle.is_dir():
        shutil.rmtree(bundle)
    for name, text in files.items():
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def _last_line(result: subprocess.CompletedProcess[str]) -> str:
    lines = [line for line in (result.stderr + result.stdout).splitlines() if line.strip()]
    return lines[-1].strip() if lines else f"exit {result.returncode}"


def check(spec: str, bundle: Path = BUNDLE, *, ci: bool) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        result = render(spec, Path(scratch), offline=not ci)
        if result.returncode != 0 and not ci:
            print(
                "cli-tools bundle check: skipped here, the pinned basicly wheel is not in the uv "
                f"cache ({_last_line(result)}); CI runs it"
            )
            return 0
        if result.returncode != 0:
            print(
                f"cli-tools bundle check: {spec} did not run: {_last_line(result)}", file=sys.stderr
            )
            return 1
        pinned = tree(Path(scratch) / ".claude" / "skills" / SKILL)
    found = differences(tree(bundle), pinned)
    if not found:
        print(f"cli-tools bundle check: {len(pinned)} files equal the pinned skill")
        return 0
    for line in found:
        print(f"cli-tools bundle check: {line}", file=sys.stderr)
    print(f"cli-tools bundle check: refresh the bundle with: {REFRESH}", file=sys.stderr)
    return 1


def refresh(spec: str, bundle: Path = BUNDLE, *, in_hook: bool = False) -> int:
    with tempfile.TemporaryDirectory() as scratch:
        result = render(spec, Path(scratch), offline=False)
        if result.returncode != 0:
            print(f"cli-tools bundle: {spec} did not run: {_last_line(result)}", file=sys.stderr)
            return 1
        files = tree(Path(scratch) / ".claude" / "skills" / SKILL)
    if not files:
        print(f"cli-tools bundle: {spec} wrote no {SKILL} skill", file=sys.stderr)
        return 1
    removed = sorted(tree(bundle).keys() - files.keys()) if in_hook else []
    if removed:
        folder = bundle.relative_to(ROOT).as_posix()
        for name in removed:
            print(f"cli-tools bundle: the new pin removes {folder}/{name}", file=sys.stderr)
        print(
            "cli-tools bundle: the commit hook cannot remove files, so nothing was written; run "
            f"{REFRESH}, then git add -A {folder}, then commit again",
            file=sys.stderr,
        )
        return REMOVES_FILES
    write_bundle(files, bundle)
    print(f"cli-tools bundle: wrote {len(files)} files to {bundle.relative_to(ROOT).as_posix()}")
    return 0


def _staged_paths() -> list[str]:
    result = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "--name-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.splitlines() if result.returncode == 0 else []


def refresh_staged(staged: list[str], spec: str, bundle: Path = BUNDLE) -> int:
    if INSTALL_STATE not in staged:
        return 0
    print(f"cli-tools bundle: {INSTALL_STATE} is staged, so the bundle follows the pin")
    code = refresh(spec, bundle, in_hook=True)
    if code == REMOVES_FILES:
        return 1
    if code != 0:
        print(
            f"cli-tools bundle: the refresh failed; run {REFRESH}, then "
            f"git add {bundle.relative_to(ROOT).as_posix()}",
            file=sys.stderr,
        )
        return 1
    added = subprocess.run(  # nosec B603 B607
        ["git", "add", "-A", "--", bundle.relative_to(ROOT).as_posix()], cwd=ROOT, check=False
    )
    return added.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bundle_cli_tools_skill.py")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args(argv)
    spec = harness.basicly_spec()
    if args.check:
        return check(spec, ci=in_ci())
    if args.staged:
        return refresh_staged(_staged_paths(), spec)
    return refresh(spec)


if __name__ == "__main__":
    sys.exit(main())
