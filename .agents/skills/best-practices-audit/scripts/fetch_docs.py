from __future__ import annotations

import argparse
import http.client
import json
import re
import sys
import tempfile
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

PLATFORM = "https://platform.claude.com/docs/en/"
CODE = "https://code.claude.com/docs/"

SOURCES = {
    "fable-prompting": (
        f"{PLATFORM}build-with-claude/prompt-engineering/prompting-claude-fable-5-2.md"
    ),
    "skills-best-practices": f"{PLATFORM}agents-and-tools/agent-skills/best-practices.md",
    "skills-overview": f"{PLATFORM}agents-and-tools/agent-skills/overview.md",
    "context-windows": f"{PLATFORM}build-with-claude/context-windows.md",
    "prompt-caching": f"{PLATFORM}build-with-claude/prompt-caching.md",
    "token-counting": f"{PLATFORM}build-with-claude/token-counting.md",
    "compaction": f"{PLATFORM}build-with-claude/compaction.md",
    "context-editing": f"{PLATFORM}build-with-claude/context-editing.md",
    "mid-conversation-system-messages": (
        f"{PLATFORM}build-with-claude/mid-conversation-system-messages.md"
    ),
    "mid-conversation-effort-example": (
        f"{PLATFORM}build-with-claude/mid-conversation-effort-example.md"
    ),
    "tool-reference": f"{PLATFORM}agents-and-tools/tool-use/tool-reference.md",
    "manage-tool-context": f"{PLATFORM}agents-and-tools/tool-use/manage-tool-context.md",
    "tool-combinations": f"{PLATFORM}agents-and-tools/tool-use/tool-combinations.md",
    "tool-use-with-prompt-caching": (
        f"{PLATFORM}agents-and-tools/tool-use/tool-use-with-prompt-caching.md"
    ),
    "claude-code-skills": f"{CODE}en/skills.md",
    "claude-code-hooks": f"{CODE}en/hooks.md",
    "claude-code-sub-agents": f"{CODE}en/sub-agents.md",
    "claude-code-memory": f"{CODE}en/memory.md",
    "claude-code-costs": f"{CODE}en/costs.md",
    "claude-code-prompt-caching": f"{CODE}en/prompt-caching.md",
    "claude-code-permissions": f"{CODE}en/permissions.md",
    "claude-code-settings": f"{CODE}en/settings.md",
    "claude-code-model-config": f"{CODE}en/model-config.md",
    "claude-code-advisor": f"{CODE}en/advisor.md",
    "claude-code-index": f"{CODE}llms.txt",
    "claude-platform-index": "https://platform.claude.com/llms.txt",
}

DISCOVERY_INDEXES = ("claude-platform-index", "claude-code-index")
DISCOVERY_LIMIT = 10
INDEX_READ_LIMIT = 2 * 1024 * 1024
MODEL_GUIDE_PATHS = {
    "platform.claude.com": re.compile(
        r"/docs/en/(?:build-with-claude/prompt-engineering/prompting-claude-[a-z0-9-]+"
        r"|models/[a-z0-9-]+/(?:migration-guide|whats-new-[a-z0-9-]+))(?:\.md)?"
    ),
    "code.claude.com": re.compile(r"/docs/en/(?:model-config|advisor|effort)(?:\.md)?"),
}

TIMEOUT_S = 20.0
COMPLETE = 0
PARTIAL = 1
OFFLINE = 3
STAMP_FILE = "FETCHED_AT"
HTTP_OK = 200
USER_AGENT = "basicly-best-practices-audit"

Fetch = Callable[[str], bytes]


def fetch(
    url: str, connect: Callable[..., http.client.HTTPConnection] = http.client.HTTPSConnection
) -> bytes:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"refusing {url!r}: only https sources are fetched")
    connection = connect(parts.hostname, timeout=TIMEOUT_S)
    try:
        connection.request("GET", parts.path, headers={"User-Agent": USER_AGENT})
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()
    if response.status != HTTP_OK:
        raise OSError(f"HTTP {response.status} {response.reason}")
    return body


def default_out() -> Path:
    return Path(tempfile.gettempdir()) / "basicly-vendor-docs"


def pull(out: Path, get: Fetch = fetch) -> tuple[list[str], list[str]]:
    out.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    failed: list[str] = []
    for name, url in SOURCES.items():
        suffix = Path(url).suffix or ".md"
        (out / f"{name}{suffix}").unlink(missing_ok=True)
        try:
            body = get(url)
        except (OSError, http.client.HTTPException) as exc:
            failed.append(f"{name}: {url}: {exc}")
            continue
        (out / f"{name}{suffix}").write_bytes(body)
        fetched.append(f"{name}: {len(body)} bytes from {url}")
    if fetched:
        (out / STAMP_FILE).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    return fetched, failed


def inside_git_tree(path: Path) -> bool:
    return any((parent / ".git").exists() for parent in [path, *path.parents])


def out_refusal(out: Path) -> str:
    if out.exists() and not out.is_dir():
        return "--out names a file; pass a directory, or omit --out for the temp default"
    if inside_git_tree(out.resolve()):
        return (
            "--out is inside a git working tree, and fetched pages must never be committed; "
            "omit --out for the temp default"
        )
    return ""


def model_guide(url: str) -> str | None:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    pattern = MODEL_GUIDE_PATHS.get(parts.netloc)
    if parts.scheme != "https" or parts.query or pattern is None:
        return None
    if not pattern.fullmatch(parts.path):
        return None
    return parts._replace(fragment="").geturl()


def discover(out: Path) -> tuple[list[str], dict[str, str], int]:
    listed = {url.removesuffix(".md") for url in SOURCES.values()}
    candidates: dict[str, str] = {}
    errors: dict[str, str] = {}
    for name in DISCOVERY_INDEXES:
        path = out / f"{name}.txt"
        try:
            if path.is_symlink():
                errors[name] = "SymlinkedIndex"
                continue
            with path.open("rb") as stream:
                raw = stream.read(INDEX_READ_LIMIT + 1)
        except OSError as error:
            errors[name] = type(error).__name__
            continue
        if len(raw) > INDEX_READ_LIMIT:
            errors[name] = "IndexReadLimit"
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            errors[name] = type(error).__name__
            continue
        for url in re.findall(r"\]\((https://[^\s)]+)\)", text):
            guide = model_guide(url)
            if guide is None:
                continue
            canonical = guide.removesuffix(".md")
            if canonical not in listed and (canonical not in candidates or guide.endswith(".md")):
                candidates[canonical] = guide
    ordered = sorted(candidates.values())
    return ordered[:DISCOVERY_LIMIT], errors, max(0, len(ordered) - DISCOVERY_LIMIT)


def main(argv: list[str] | None = None, get: Fetch = fetch) -> int:
    parser = argparse.ArgumentParser(
        description="Download the current vendor pages that the best-practices audit reads."
    )
    parser.add_argument("--out", type=Path, default=default_out(), help="the directory to fill")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--list", action="store_true", help="print the sources and exit")
    modes.add_argument(
        "--discover",
        action="store_true",
        help="report model guides from saved indexes without fetching",
    )
    args = parser.parse_args(argv)
    if args.list:
        for name, url in SOURCES.items():
            print(f"{name}\t{url}")
        return COMPLETE
    refusal = out_refusal(args.out)
    if refusal:
        parser.error(refusal)
    if args.discover:
        candidates, errors, omitted = discover(args.out)
        print(
            json.dumps(
                {
                    "candidates": candidates,
                    "failed_indexes": list(errors),
                    "index_errors": errors,
                    "omitted": omitted,
                    "downloaded": False,
                },
                indent=2,
            )
        )
        return PARTIAL if errors or omitted else COMPLETE
    fetched, failed = pull(args.out, get)
    for line in fetched:
        print(f"fetched {line}")
    for line in failed:
        print(f"failed {line}", file=sys.stderr)
    if not fetched:
        print(
            "offline: no page was fetched. Audit against references/checklist.md only, "
            "and say in the first line of the report that the docs were not refreshed.",
            file=sys.stderr,
        )
        return OFFLINE
    print(f"docs: {len(fetched)} of {len(SOURCES)} pages in {args.out}")
    return PARTIAL if failed else COMPLETE


if __name__ == "__main__":
    raise SystemExit(main())
