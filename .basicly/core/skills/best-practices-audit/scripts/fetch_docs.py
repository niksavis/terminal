from __future__ import annotations

import argparse
import http.client
import sys
import tempfile
import urllib.parse
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

PLATFORM = "https://platform.claude.com/docs/en/"
CODE = "https://code.claude.com/docs/"

SOURCES = {
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
    "claude-code-index": f"{CODE}llms.txt",
}

TIMEOUT_S = 20.0
COMPLETE = 0
PARTIAL = 1
OFFLINE = 2
STAMP_FILE = "FETCHED_AT"
HTTP_OK = 200
USER_AGENT = "basicly-best-practices-audit"

Fetch = Callable[[str], bytes]


def fetch(url: str) -> bytes:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError(f"refusing {url!r}: only https sources are fetched")
    connection = http.client.HTTPSConnection(parts.hostname, timeout=TIMEOUT_S)
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
        try:
            body = get(url)
        except (OSError, http.client.HTTPException) as exc:
            failed.append(f"{name}: {url}: {exc}")
            continue
        suffix = Path(url).suffix or ".md"
        (out / f"{name}{suffix}").write_bytes(body)
        fetched.append(f"{name}: {len(body)} bytes from {url}")
    if fetched:
        (out / STAMP_FILE).write_text(datetime.now(UTC).isoformat() + "\n", encoding="utf-8")
    return fetched, failed


def main(argv: list[str] | None = None, get: Fetch = fetch) -> int:
    parser = argparse.ArgumentParser(
        description="Download the current vendor pages that the best-practices audit reads."
    )
    parser.add_argument("--out", type=Path, default=default_out(), help="the directory to fill")
    parser.add_argument("--list", action="store_true", help="print the sources and exit")
    args = parser.parse_args(argv)
    if args.list:
        for name, url in SOURCES.items():
            print(f"{name}\t{url}")
        return COMPLETE
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
