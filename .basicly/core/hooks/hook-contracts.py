from __future__ import annotations

import ast
import sys
from pathlib import Path


def findings(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
        compile(tree, path.name, "exec")
    except (OSError, UnicodeError, SyntaxError) as error:
        return [f"{path.name}: syntax or source error: {error}"]
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        text = keywords.get("text", keywords.get("universal_newlines"))
        encoding = keywords.get("encoding")
        if (
            isinstance(text, ast.Constant)
            and text.value is True
            and (
                encoding is None
                or (
                    isinstance(encoding, ast.Constant)
                    and (not isinstance(encoding.value, str) or not encoding.value)
                )
            )
        ):
            errors.append(
                f"{path.name}:{node.lineno}: text subprocess calls need an explicit encoding"
            )
    return errors


def main() -> int:
    paths = sorted(Path(__file__).resolve().parent.glob("*.py"))
    errors = [error for path in paths for error in findings(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"hook contracts passed: {len(paths)} Python hooks checked for syntax and encoding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
