from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import NamedTuple

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
lexer = _load("lexer.py", "basicly_comments_kit_lexer")
directives = _load("directives.py", "basicly_comments_kit_directives")
python_source = _load("python_source.py", "basicly_comments_kit_python_source")

LexError = lexer.LexError


class Finding(NamedTuple):
    path: Path
    line: int
    text: str
    span: object


def is_covered(path: Path) -> bool:
    suffix = path.suffix.lower()
    return languages.is_python(suffix) or languages.for_suffix(suffix) is not None


def all_spans(path: Path, source: str) -> list:

    suffix = path.suffix.lower()
    if languages.is_python(suffix):
        return python_source.comment_spans(source)
    language = languages.for_suffix(suffix)
    if language is None:
        raise ValueError(f"{path}: the comments kit claims no language for {suffix!r}")
    return lexer.comment_spans(source, language)


def findings(path: Path, source: str) -> list:
    return [
        Finding(path, span.line, span.text(source), span)
        for span in all_spans(path, source)
        if not directives.is_directive(span.text(source))
    ]


def strippable_spans(path: Path, source: str) -> list:
    return [finding.span for finding in findings(path, source)]
