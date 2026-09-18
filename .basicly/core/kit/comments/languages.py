from __future__ import annotations

from typing import NamedTuple


class StringRule(NamedTuple):
    open: str
    close: str
    escapes: bool


class Language(NamedTuple):
    name: str
    extensions: tuple[str, ...]
    line_comments: tuple[str, ...]
    block_comments: tuple[tuple[str, str], ...]
    strings: tuple[StringRule, ...]
    regex_literals: bool
    word_boundary: bool = False
    heredocs: bool = False


_QUOTES = (StringRule("'", "'", True), StringRule('"', '"', True))
_QUOTES_AND_TEMPLATE = (*_QUOTES, StringRule("`", "`", True))

C_LIKE = Language(
    name="c-like",
    extensions=(
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".cs",
        ".go",
        ".java",
        ".kt",
        ".kts",
        ".m",
        ".mm",
        ".php",
        ".rs",
        ".scala",
        ".swift",
    ),
    line_comments=("//",),
    block_comments=(("/*", "*/"),),
    strings=_QUOTES,
    regex_literals=False,
)

JAVASCRIPT = Language(
    name="javascript",
    extensions=(".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"),
    line_comments=("//",),
    block_comments=(("/*", "*/"),),
    strings=_QUOTES_AND_TEMPLATE,
    regex_literals=True,
)

CSS = Language(
    name="css",
    extensions=(".css",),
    line_comments=(),
    block_comments=(("/*", "*/"),),
    strings=_QUOTES,
    regex_literals=False,
)

SASS = Language(
    name="sass",
    extensions=(".scss", ".sass", ".less"),
    line_comments=("//",),
    block_comments=(("/*", "*/"),),
    strings=_QUOTES,
    regex_literals=False,
)

HTML = Language(
    name="html",
    extensions=(".html", ".htm", ".xhtml", ".vue", ".svelte", ".cshtml", ".razor"),
    line_comments=(),
    block_comments=(("<!--", "-->"),),
    strings=(),
    regex_literals=False,
)

SHELL = Language(
    name="shell",
    extensions=(".sh", ".bash", ".zsh", ".ksh"),
    line_comments=("#",),
    block_comments=(),
    strings=(StringRule("'", "'", False), StringRule('"', '"', True)),
    regex_literals=False,
    word_boundary=True,
    heredocs=True,
)

POWERSHELL = Language(
    name="powershell",
    extensions=(".ps1", ".psm1", ".psd1"),
    line_comments=("#",),
    block_comments=(("<#", "#>"),),
    strings=(StringRule("'", "'", False), StringRule('"', '"', True)),
    regex_literals=False,
    word_boundary=True,
)

SQL = Language(
    name="sql",
    extensions=(".sql",),
    line_comments=("--",),
    block_comments=(("/*", "*/"),),
    strings=(StringRule("'", "'", False),),
    regex_literals=False,
)

VISUAL_BASIC = Language(
    name="visual-basic",
    extensions=(".vb", ".vbs"),
    line_comments=("'",),
    block_comments=(),
    strings=(StringRule('"', '"', False),),
    regex_literals=False,
)

PYTHON_EXTENSIONS = (".py", ".pyi")

LANGUAGES = (
    C_LIKE,
    JAVASCRIPT,
    CSS,
    SASS,
    HTML,
    SHELL,
    POWERSHELL,
    SQL,
    VISUAL_BASIC,
)

_BY_EXTENSION = {extension: language for language in LANGUAGES for extension in language.extensions}


def is_python(suffix: str) -> bool:
    return suffix.lower() in PYTHON_EXTENSIONS


def for_suffix(suffix: str):
    return _BY_EXTENSION.get(suffix.lower())


def covered_suffixes() -> tuple[str, ...]:
    return tuple(sorted(set(_BY_EXTENSION) | set(PYTHON_EXTENSIONS)))
