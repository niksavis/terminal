from __future__ import annotations

import os
import re
import subprocess  # nosec B404
import sys


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec B603 B607
        ["git", *args], capture_output=True, text=True, encoding="utf-8", check=False
    )


def _commit(value: str, name: str) -> str:
    if re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value) and set(value) != {"0"}:
        found = _git("rev-parse", "--verify", f"{value}^{{commit}}")
        if found.returncode == 0:
            return found.stdout.strip()
    raise ValueError(f"{name} must be a full available commit SHA")


def selected_range(event: str, head: str, base: str, before: str, audit: str) -> str:
    if audit not in ("", "false", "true"):
        raise ValueError("all_history must be true or false")
    if audit == "true" and (event != "workflow_dispatch" or base):
        raise ValueError("all_history is only for manual audits without a base")
    head = _commit(head, "head")
    if event == "workflow_dispatch":
        if audit == "true":
            return head
        if not base:
            raise ValueError(
                "manual runs require input base with a full ancestor commit SHA; "
                "set all_history=true only for an intentional history audit"
            )
    elif event == "push":
        if not before or set(before) == {"0"}:
            raise ValueError(
                "push before is missing; run manually with input base, "
                "or all_history=true for an intentional audit"
            )
        base = before
    elif event != "pull_request":
        raise ValueError("event must be push pull_request or workflow_dispatch")
    base = _commit(base, "base" if event != "push" else "push before")
    relation = (
        _git("merge-base", "--is-ancestor", base, head)
        if event == "workflow_dispatch"
        else _git("merge-base", base, head)
    )
    if relation.returncode != 0:
        raise ValueError("manual base must be an ancestor; push and PR commits must share history")
    span = f"{base}..{head}"
    count = _git("rev-list", "--count", span)
    if count.returncode != 0 or not count.stdout.strip().isdigit():
        raise ValueError("cannot enumerate the selected commit range")
    if int(count.stdout.strip()) == 0:
        raise ValueError("the selected range contains no commits")
    return span


def main() -> int:
    try:
        span = selected_range(
            os.environ.get("BASICLY_CI_EVENT", ""),
            os.environ.get("BASICLY_CI_HEAD", ""),
            os.environ.get("BASICLY_CI_BASE", ""),
            os.environ.get("BASICLY_CI_BEFORE", ""),
            os.environ.get("BASICLY_CI_ALL_HISTORY", ""),
        )
    except ValueError as error:
        print(f"commit scope refused: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("commit scope refused: Git could not start; install Git on PATH", file=sys.stderr)
        return 1
    print(span)
    return 0


if __name__ == "__main__":
    sys.exit(main())
