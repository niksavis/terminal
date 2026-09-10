"""Fail when a kit module reaches back into basicly (basicly-vkh0.16).

The kit under ``.basicly/core/kit`` is the portable half of this harness: the tier
resolver, its host hook, and the work-tracker store. Its one structural rule
(``.basicly/core/kit/tracker/SPEC.md`` §4) is that **the dependency direction is one-way** —
the engine imports the kit; the kit imports nothing. Stated there in full: the kit
may not read basicly's config loader, its logging, its session state or its policy
module. It reads its own committed data and takes everything else as arguments.

That design also claimed the direction was already enforced, because ``lint-imports``
is a live ``[[verify.checks]]`` entry. **It was not, and could not be.** import-linter
analyses one ``root_package``, declared as ``basicly`` in ``.importlinter``, with
containers ``basicly`` and ``basicly.renderers``. The kit is flat modules with no
``__init__.py``, it is not importable as part of that package, and it is not on
``sys.path`` — so import-linter never opens a kit file. The claim was unenforceable
rather than merely unimplemented, which is this repo's own worst gate shape: a
fail-open check is indistinguishable from a pass. This script is the gate that can
actually see the kit tree, and ``tests/test_kit_boundary.py`` seeds one violation of
every class below so it is proven to discriminate rather than to pass vacuously.

Four violation classes, chosen because they are the four routes into the engine that
a file with no ``import basicly`` still has:

``imports-basicly``
    A static ``import basicly...`` / ``from basicly... import ...``. Matched on the
    AST, so the many docstrings here that *write* "no ``import basicly``" as prose
    are not findings.
``dynamic-import-basicly``
    ``importlib.import_module("basicly...")``, ``importlib.util.find_spec(...)`` or
    ``__import__(...)``. Not hypothetical: ``tracker/events.py`` already loads its
    sibling ``ids.py`` through ``importlib``, so this route is live in this tree and
    a static-import-only rule would be trivially walked around.
``reads-engine-source``
    A path naming a file inside the engine package (``src/basicly/…``,
    ``basicly/<module>.py``) — the ``spec_from_file_location`` / ``read_text`` route
    to exactly the config loader, logging, session state and policy modules the
    design names. Matched on any engine module rather than a list of the four, so it
    cannot go stale when a fifth is added.
``reads-engine-state``
    ``basicly.toml`` (the config loader's input) or a ``.basicly/<dir>`` path outside
    ``.basicly/core``. An **allow-list**, so it fails closed: ``.basicly/ledger`` and
    ``.basicly/usage`` are engine ledgers, and a kit store added at ``.basicly/<new>``
    has to be declared in ``_KIT_DATA_DIRS`` by a maintainer rather than sliding in.

Path expressions are folded before matching (``Path(".basicly") / "core"``,
``os.path.join``, ``.joinpath``), because that is the idiom the kit actually uses —
``tier_resolver.CORE_DIR`` is written exactly that way, and a rule that only read
whole string literals would be nearly dead on this tree.

Where it stops, stated so it is not mistaken for more than it is: a path whose
segment is computed at runtime (``f".basicly/{name}"``) and a module name assembled
from pieces are not detected, and neither is a ``subprocess`` call to the ``basicly``
CLI — the kit's no-subprocess rule is a separate one, and this gate does not claim
it. Static analysis of literals is the floor, not the ceiling.

**stdlib only**, by the hooks convention — the hook ships to consumers with the kit,
which is what makes the boundary travel rather than staying a fact about this repo.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_runner import project_root

# The kit tree, relative to the repo root.
KIT_ROOT = Path(".basicly") / "core" / "kit"

# Subdirectories of `.basicly` the kit owns and may read. Everything else under
# `.basicly` is engine state; adding a kit store means adding it here on purpose.
_KIT_DATA_DIRS = frozenset({"core"})

# Dynamic-import callables whose first string argument is a module name.
_IMPORT_CALLS = frozenset({"__import__", "import_module", "find_spec"})

# Callables that build a path from string parts.
_PATH_CALLS = frozenset({"Path", "PurePath", "PurePosixPath", "PureWindowsPath"})
_JOIN_CALLS = frozenset({"join", "joinpath"})

# A file inside the engine package. The leading `(?<![.\w])` is what keeps
# `.basicly/core/...` — the kit's own root — from reading as the package.
_ENGINE_SOURCE = re.compile(r"(?<![.\w])(?:src[/\\]basicly[/\\]|basicly[/\\][A-Za-z_]\w*\.py)")

# The engine's committed config, and the gitignored local overlay beside it.
_ENGINE_CONFIG = re.compile(r"(?<![\w./\\-])basicly(?:\.local)?\.toml\b")

# `.basicly/<segment>` — the segment decides, against the allow-list above.
_DOT_BASICLY = re.compile(r"\.basicly[/\\]([A-Za-z0-9_.-]+)")


class Finding(NamedTuple):
    """One boundary violation, reported as ``path:line: rule: detail``."""

    path: str
    lineno: int
    rule: str
    detail: str

    def __str__(self) -> str:
        """The reported line, in the ``path:line: rule: detail`` shape hooks here use."""
        return f"{self.path}:{self.lineno}: {self.rule}: {self.detail}"


def kit_modules(kit_root: Path) -> list[Path]:
    """Every Python module in the kit tree, lexicographically, caches excluded."""
    return sorted(
        path
        for path in kit_root.rglob("*.py")
        if "__pycache__" not in path.parts and path.is_file()
    )


def _root_package(name: str) -> str:
    """The top-level package a dotted module name belongs to."""
    return name.split(".", 1)[0]


def _callee(node: ast.Call) -> str:
    """The attribute or bare name a call targets (``import_module``, ``Path``, …)."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _path_text(node: ast.expr) -> str | None:
    """The literal path an expression denotes, or None when it is not all literals.

    Folds the three shapes that build a path out of parts, so a rule written against
    whole strings still sees ``Path(".basicly") / "core"``. Separators are normalised
    to ``/``; the patterns accept either, so a Windows-style literal still matches.
    """
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _join_parts([node.left, node.right])
    if isinstance(node, ast.Call):
        callee = _callee(node)
        if callee in _PATH_CALLS and node.args:
            return _join_parts(node.args)
        if callee in _JOIN_CALLS:
            base = node.func.value if isinstance(node.func, ast.Attribute) else None
            parts = [base, *node.args] if callee == "joinpath" and base else list(node.args)
            return _join_parts(parts) if parts else None
    return None


def _join_parts(operands: list[ast.expr]) -> str | None:
    """``a/b/c`` for operands that are all literal path parts; None if any is not.

    ``operands`` rather than the obvious ``nodes``: ``.scripts/wired_or_deleted.py``
    counts an identifier anywhere outside ``tests/`` as a read of a same-named record
    field, so a local called ``nodes`` here silently retires the suppression on
    ``basicly.loop_state.Ranking.nodes`` and that gate goes red for an unrelated file.
    """
    parts = [_path_text(operand) for operand in operands]
    if any(part is None for part in parts):
        return None
    return "/".join(part for part in parts if part is not None)


def _statement_strings(tree: ast.Module) -> set[int]:
    """Ids of the string constants that are bare expression statements.

    Docstrings and stray prose. They are excluded from the path rules: this file's
    own neighbours describe the boundary in prose, and a sentence about
    ``basicly/config.py`` is documentation, not a read of it.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            ids.add(id(node.value))
    return ids


def _import_findings(rel: str, tree: ast.Module) -> list[Finding]:
    """Static and dynamic imports of the engine package."""
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            findings += [
                Finding(rel, node.lineno, "imports-basicly", f"import {alias.name}")
                for alias in node.names
                if _root_package(alias.name) == "basicly"
            ]
        elif isinstance(node, ast.ImportFrom):
            if node.module and _root_package(node.module) == "basicly":
                findings.append(
                    Finding(rel, node.lineno, "imports-basicly", f"from {node.module} import ...")
                )
        elif isinstance(node, ast.Call) and _callee(node) in _IMPORT_CALLS and node.args:
            target = node.args[0]
            if (
                isinstance(target, ast.Constant)
                and isinstance(target.value, str)
                and _root_package(target.value) == "basicly"
            ):
                findings.append(
                    Finding(
                        rel,
                        node.lineno,
                        "dynamic-import-basicly",
                        f"{_callee(node)}({target.value!r})",
                    )
                )
    return findings


def _path_rule(text: str) -> str | None:
    """The rule a literal path trips, or None when it names nothing of the engine's."""
    if _ENGINE_SOURCE.search(text):
        return "reads-engine-source"
    outside_kit = (match := _DOT_BASICLY.search(text)) and match.group(1) not in _KIT_DATA_DIRS
    if _ENGINE_CONFIG.search(text) or outside_kit:
        return "reads-engine-state"
    return None


def _path_findings(rel: str, tree: ast.Module) -> list[Finding]:
    """Reads of the engine's source tree, its config, or its state directories."""
    skip = _statement_strings(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.expr) or id(node) in skip:
            continue
        text = _path_text(node)
        if text and (rule := _path_rule(text)):
            findings.append(Finding(rel, node.lineno, rule, text))
    return _dedupe(findings)


def _dedupe(findings: list[Finding]) -> list[Finding]:
    """Drop repeats of one rule on one line — a folded path re-reports its leaves."""
    seen: set[tuple[int, str]] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = (finding.lineno, finding.rule)
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    return unique


def module_findings(module: Path, rel: str) -> list[Finding]:
    """Every boundary violation in one kit module.

    A module that will not parse is itself a finding rather than a skip: a gate that
    silently passes what it could not read is the fail-open shape this replaces.
    """
    source = module.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(module))
    except SyntaxError as exc:
        return [Finding(rel, exc.lineno or 1, "unparseable", exc.msg)]
    return _import_findings(rel, tree) + _path_findings(rel, tree)


def scan(kit_root: Path, repo_root: Path | None = None) -> list[Finding]:
    """Every violation in the kit tree, ordered by module then line."""
    base = repo_root or kit_root
    findings: list[Finding] = []
    for module in kit_modules(kit_root):
        try:
            rel = module.relative_to(base).as_posix()
        except ValueError:
            rel = module.as_posix()
        findings += module_findings(module, rel)
    return findings


def main(argv: list[str] | None = None) -> int:
    """Fail when any kit module reaches back into basicly."""
    parser = argparse.ArgumentParser(description="Gate the one-way kit boundary.")
    parser.add_argument(
        "--kit-root",
        type=Path,
        default=None,
        help=f"kit tree to scan (default: {KIT_ROOT.as_posix()} under the repo root)",
    )
    args = parser.parse_args(argv)

    repo_root = project_root()
    kit_root = args.kit_root or repo_root / KIT_ROOT
    if not kit_root.is_dir():
        print(f"kit-boundary: no kit tree at {kit_root}; nothing to gate.")
        return 0

    findings = scan(kit_root, repo_root)
    if not findings:
        return 0

    print(
        "kit-boundary: the kit reaches back into basicly — the dependency direction "
        "is one-way (.basicly/core/kit/tracker/SPEC.md §4).",
        file=sys.stderr,
    )
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    print(
        "The kit is copied into repositories that have never heard of this harness, "
        "so an engine import or read makes it unusable there.\n"
        "Take the value as an argument instead, or read it from the kit's own "
        "committed data under .basicly/core.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
