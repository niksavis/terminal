from __future__ import annotations

import os
import re
import subprocess  # nosec B404
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TESTS = Path("tests")
BASE_REF = "origin/main"
_PACKAGES = ("terminal_setup",)
BUNDLE_CHECK = ".scripts/bundle_cli_tools_skill.py"


def in_ci(environ: dict[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get("CI", "")
    return value.strip().lower() not in {"", "0", "false", "no"}


def _module_name(path: Path) -> str | None:
    if path.suffix != ".py" or not path.parts or path.parts[0] not in _PACKAGES:
        return None
    parts = list(path.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports_module(text: str, module: str) -> bool:
    if re.search(rf"\b{re.escape(module)}\b(?!\.\w)", text):
        return True
    parent, _, name = module.rpartition(".")
    if not parent:
        return False
    pattern = rf"from\s+{re.escape(parent)}\s+import\s+\(?[^)]*?\b{re.escape(name)}\b"
    return re.search(pattern, text, re.DOTALL) is not None


def _references(text: str, path: Path) -> bool:
    module = _module_name(path)
    if module is not None:
        return _imports_module(text, module)
    names = {path.name}
    if path.suffix == ".py":
        names.add(path.stem)
        names.add(path.stem.replace("-", "_"))
    return any(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) for name in names)


def _is_test_file(path: Path) -> bool:
    return (
        path.parts[:1] == (TESTS.name,) and path.name.startswith("test_") and path.suffix == ".py"
    )


def select_tests(changed: list[Path], tests: dict[Path, str]) -> dict[Path, str]:
    selected: dict[Path, str] = {}
    for path in changed:
        if _is_test_file(path) and path in tests:
            selected.setdefault(path, "changed")
    for path in changed:
        if _is_test_file(path) or path.name == "conftest.py":
            continue
        for test, text in sorted(tests.items()):
            if test not in selected and _references(text, path):
                selected[test] = f"uses {path.as_posix()}"
    return dict(sorted(selected.items()))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec
        ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )


def changed_files() -> list[Path] | None:
    base = _git("merge-base", BASE_REF, "HEAD")
    if base.returncode != 0:
        return None
    diff = _git("diff", "--name-only", base.stdout.strip(), "HEAD")
    if diff.returncode != 0:
        return None
    return [Path(line) for line in diff.stdout.splitlines() if line.strip()]


def _test_texts() -> dict[Path, str]:
    root = PROJECT_ROOT / TESTS
    return {
        path.relative_to(PROJECT_ROOT): path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(root.rglob("test_*.py"))
    }


def _pytest(*targets: str) -> int:
    print("==> pytest " + (" ".join(targets) if targets else "(whole suite)"))
    start = time.perf_counter()
    result = subprocess.run(
        ["uv", "run", "pytest", *(targets or (str(TESTS) + "/",))],
        cwd=PROJECT_ROOT,
        check=False,
    )  # nosec
    elapsed = time.perf_counter() - start
    if result.returncode == 0:
        print(f"pre-push passed in {elapsed:.2f}s")
    else:
        print(f"pre-push failed in {elapsed:.2f}s", file=sys.stderr)
    return result.returncode


def _bundle_check() -> int:
    print("==> cli-tools bundle check")
    return subprocess.run(  # nosec
        ["uv", "run", "python", BUNDLE_CHECK, "--check"], cwd=PROJECT_ROOT, check=False
    ).returncode


def main() -> int:
    if _bundle_check() != 0:
        print("pre-push failed: the cli-tools bundle check", file=sys.stderr)
        return 1
    if in_ci():
        return _pytest()
    changed = changed_files()
    if changed is None:
        print(
            f"pre-push: cannot compare HEAD with {BASE_REF}; run git fetch origin, then push again",
            file=sys.stderr,
        )
        return 1
    selected = select_tests(changed, _test_texts())
    print(
        f"pre-push: {len(changed)} files changed against {BASE_REF}; "
        f"{len(selected)} test files run here, CI runs the whole suite"
    )
    if not selected:
        print("pre-push: no test file maps to the changed files; nothing to run here")
        return 0
    for test, reason in selected.items():
        print(f"  {test.as_posix()}: {reason}")
    return _pytest(*(test.as_posix() for test in selected))


if __name__ == "__main__":
    sys.exit(main())
