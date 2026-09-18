from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str):
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError("the comments kit's " + file_name + " is missing from beside it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


languages = _load("languages.py", "basicly_comments_kit_languages")
python_source = _load("python_source.py", "basicly_comments_kit_python_source")
scan = _load("scan.py", "basicly_comments_kit_scan")

_QUOTED = re.compile(r"'[^'\n]*'|\"[^\"\n]*\"")


class UnsafeStripError(Exception):
    pass


def strip_source(path: Path, source: str) -> str:
    stripped = _apply(source, scan.strippable_spans(path, source))
    _prove(path, source, stripped)
    return stripped


def _apply(source: str, spans) -> str:
    if not spans:
        return source
    return _drop_emptied_lines(source, _blank_out(source, spans))


def _blank_out(source: str, spans) -> str:

    pieces = []
    cursor = 0
    for span in sorted(spans):
        pieces.append(source[cursor : span.start])
        pieces.append(span.replacement)
        pieces.append("\n" * source.count("\n", span.start, span.end))
        cursor = span.end
    pieces.append(source[cursor:])
    return "".join(pieces)


def _drop_emptied_lines(before: str, after: str) -> str:
    originals = before.split("\n")
    kept = []
    for index, line in enumerate(after.split("\n")):
        if line.strip() or not originals[index].strip():
            kept.append(line)
    return "\n".join(kept)


def _prove(path: Path, before: str, after: str) -> None:
    if languages.is_python(path.suffix.lower()):
        _prove_python(path, before, after)
    _prove_idempotent(path, after)
    _prove_literals(path, before, after)


def _prove_python(path: Path, before: str, after: str) -> None:
    if not python_source.parses(after):
        raise UnsafeStripError(f"{path}: the stripped source no longer parses")
    if python_source.tree_without_docstrings(before) != python_source.tree_without_docstrings(
        after
    ):
        raise UnsafeStripError(f"{path}: the strip changed the syntax tree, not only its prose")


def _prove_idempotent(path: Path, after: str) -> None:
    if _apply(after, scan.strippable_spans(path, after)) != after:
        raise UnsafeStripError(f"{path}: a second strip changes the output, so the first is unsafe")


def _prove_literals(path: Path, before: str, after: str) -> None:
    original = set(_QUOTED.findall(before))
    for literal in _QUOTED.findall(after):
        if literal not in original:
            raise UnsafeStripError(f"{path}: the strip invented the literal {literal!r}")
