from __future__ import annotations

import re
import subprocess  # nosec B404
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shell_tokens import segment_tokens, split_pipeline_segments, strip_heredocs

ALLOWED = (
    "run the one test file you changed, for example uv run pytest tests/test_x.py -q, "
    "or the staged checks: uv run basicly verify --mode staged --affected; "
    "CI runs the full suite on the pull request"
)
_PYTEST_VALUE_FLAGS = frozenset({
    "-k",
    "-m",
    "-n",
    "-p",
    "-c",
    "-o",
    "-W",
    "-r",
    "--rootdir",
    "--deselect",
    "--ignore",
    "--maxfail",
    "--tb",
    "--durations",
    "--basetemp",
    "--confcutdir",
    "--dist",
})
_RUNNERS = frozenset({"uv", "uvx", "python", "python3", "env", "timeout", "nice"})
_NPM = frozenset({"npm", "pnpm", "yarn"})
_ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
_REDIRECT = re.compile(r"^(?:\d+|&)?(?:>>?|<|>&|<&)(?P<target>.*)$")


def _strip(tokens: list[str]) -> list[str]:
    while tokens and _ASSIGN.match(tokens[0]):
        tokens = tokens[1:]
    while tokens and Path(tokens[0]).name in _RUNNERS:
        tokens = tokens[1:]
        while tokens and (tokens[0] in {"run", "-m", "--"} or tokens[0].startswith("-")):
            skip = 2 if tokens[0] in {"--with", "--from", "--python", "-k", "-s"} else 1
            tokens = tokens[skip:]
        if tokens and tokens[0].isdigit():
            tokens = tokens[1:]
    return tokens


def _paths(args: list[str]) -> list[str]:
    found, rest = [], list(args)
    while rest:
        head = rest.pop(0)
        redirect = _REDIRECT.match(head)
        if redirect:
            rest = rest[1:] if not redirect["target"] else rest
        elif head in _PYTEST_VALUE_FLAGS:
            rest = rest[1:]
        elif not head.startswith("-") and "=" not in head:
            found.append(head.split("::", 1)[0])
    return found


def _pytest(args: list[str], changed: frozenset[str]) -> str | None:
    paths = _paths(args)
    if not paths:
        return "pytest with no test file runs the whole suite"
    folders = [path for path in paths if not path.endswith(".py")]
    if folders:
        return f"pytest over the folder {folders[0]} runs a test set"
    unchanged = [path for path in dict.fromkeys(paths) if path not in changed]
    if len(set(paths)) > 1 and unchanged:
        count = len(set(paths))
        return f"pytest over {count} test files, {len(unchanged)} of them unchanged, is a test set"
    return None


def _npm(tokens: list[str]) -> str | None:
    words = tokens[1:]
    if words[:1] == ["run"]:
        words = words[1:]
    if not words or words[0] != "test":
        return None
    files = [word for word in words[1:] if word != "--" and not word.startswith("-")]
    return None if files else f"{tokens[0]} test with no test file runs the whole suite"


def _basicly(words: list[str]) -> str | None:
    if words[:1] == ["consumer-proof"]:
        return "basicly consumer-proof runs the consumer proof, which CI runs"
    if words[:1] == ["verify"]:
        joined = " ".join(words)
        if re.search(r"--mode[ =]full\b", joined):
            return "basicly verify --mode full runs the full suite"
    return None


def segment_refusal(tokens: list[str], changed: frozenset[str]) -> str | None:
    tokens = _strip(tokens)
    if not tokens:
        return None
    head = Path(tokens[0]).name
    if head in {"pytest", "py.test"}:
        return _pytest(tokens[1:], changed)
    if head in _NPM:
        return _npm(tokens)
    if head == "basicly":
        return _basicly(tokens[1:])
    return None


def refusal(command: str, changed: frozenset[str] = frozenset()) -> str | None:
    for segment in split_pipeline_segments(strip_heredocs(command)):
        found = segment_refusal(segment_tokens(segment), changed)
        if found:
            return f"{found}: {segment.strip()!r}"
    return None


def changed_files(cwd: Path) -> frozenset[str]:
    try:
        shown = subprocess.run(  # nosec B603 B607
            ["git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=all"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=5,
        )
    except OSError, subprocess.TimeoutExpired:
        return frozenset()
    if shown.returncode != 0:
        return frozenset()
    return frozenset(line[3:].split(" -> ")[-1] for line in shown.stdout.splitlines() if line)
