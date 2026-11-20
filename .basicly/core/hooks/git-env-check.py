from __future__ import annotations

import ast
import re
import subprocess  # nosec B404
import sys

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
_FIX = (
    "pass an env without the GIT_ variables, for example "
    "env={key: value for key, value in os.environ.items() if not key.startswith('GIT_')}; "
    "a hook runs tests with GIT_DIR set, and git then acts on the real repository. "
    "This check reads Python only and sees a git argv given as a list or tuple literal, "
    "a name assigned one in the same file, or a string that starts with 'git '; it does "
    "not see an argv built by a function, os.system or another process library, or "
    "tests in other languages"
)


def _starts_with_git(node: ast.AST, named: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in named
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.startswith("git ")
    if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
        return False
    head = node.elts[0]
    return isinstance(head, ast.Constant) and head.value == "git"


def _git_names(tree: ast.AST) -> set[str]:
    return {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and _starts_with_git(node.value, set())
        for target in node.targets
        if isinstance(target, ast.Name)
    }


def _is_environ(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def _copies_environ(value: ast.AST) -> bool:
    if "GIT_" in ast.unparse(value):
        return False
    for node in ast.walk(value):
        if isinstance(node, ast.Dict) and any(
            key is None and _is_environ(item)
            for key, item in zip(node.keys, node.values, strict=True)
        ):
            return True
        if isinstance(node, ast.Call) and any(_is_environ(arg) for arg in node.args):
            return True
        if isinstance(node, ast.Attribute) and _is_environ(node.value) and node.attr != "get":
            return node.attr in {"copy", "items"}
    return _is_environ(value)


def _keeps_git_variables(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg == "env":
            return _copies_environ(keyword.value)
    return True


def leaking_calls(source: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    named = _git_names(tree)
    return sorted(
        (node.lineno, node.end_lineno or node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and node.args
        and _starts_with_git(node.args[0], named)
        and _keeps_git_variables(node)
    )


def added_lines(diff: str) -> set[int]:
    lines: set[int] = set()
    for match in _HUNK.finditer(diff):
        start, count = int(match[1]), int(match[2] or "1")
        lines.update(range(start, start + count) if count else (start, start + 1))
    return lines


def _staged(path: str) -> tuple[str, str]:
    shown = subprocess.run(  # nosec B603 B607
        ["git", "show", f":{path}"], capture_output=True, text=True, encoding="utf-8", check=False
    )
    diff = subprocess.run(  # nosec B603 B607
        ["git", "diff", "--cached", "-U0", "--", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return shown.stdout, diff.stdout


def main(paths: list[str]) -> int:
    found = []
    for path in paths:
        source, diff = _staged(path)
        new = added_lines(diff)
        found.extend(
            f"{path}:{start}"
            for start, end in leaking_calls(source)
            if new.intersection(range(start, end + 1))
        )
    for place in found:
        print(
            f"git-env: {place} runs git with the inherited GIT_ variables; {_FIX}", file=sys.stderr
        )
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
