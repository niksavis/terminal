from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from orch_lessons.log import RefusedError

VENDORS = ("claude", "copilot", "codex")
ROLE_FILES = Path(".agents/roles")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
ADAPTER = Path("bin") / "session"
WORKER = "worker"
ORCHESTRATOR = "orchestrator"
ADAPTER_VENDORS = ("claude", "codex")
PRINTED = (
    "printed, not started: orch start starts only --role worker, through the session "
    "adapter; run the command below to start a {vendor} session with role {role}"
)


@dataclass(frozen=True)
class Plan:
    argv: list[str]
    run: bool
    note: str


def _name(name: str) -> None:
    if CONTROL.search(name) or not name.strip():
        raise RefusedError(
            "orch start refuses --name: give a non-empty name with no control characters"
        )


def launch(vendor: str, role: str, name: str, repo: Path) -> list[str]:
    _name(name)
    if vendor == "claude":
        return ["claude", "--agent", role, "-n", name]
    if vendor == "copilot":
        return ["copilot", "--agent", role]
    if vendor == "codex":
        role_file = repo / ROLE_FILES / f"{role}.md"
        if not role_file.is_file():
            raise RefusedError(
                f"{ROLE_FILES / (role + '.md')} is missing in {repo}; turn on the "
                "orchestration feature of basicly and run basicly install"
            )
        text = role_file.read_text(encoding="utf-8")
        return ["codex", "-c", f"developer_instructions={json.dumps(text)}"]
    raise RefusedError(f"orch start refuses vendor {vendor!r}; use one of: {', '.join(VENDORS)}")


@dataclass(frozen=True)
class Request:
    vendor: str
    role: str
    name: str
    folder: Path | None = None
    prompt: str | None = None


def _worker(ask: Request, store_root: Path | None) -> Plan:
    _name(ask.name)
    adapter = store_root / ADAPTER if store_root is not None else Path(".orchestrator") / ADAPTER
    usage = f"{adapter} start NAME --dir DIR [--codex] [--prompt FILE]"
    if store_root is None or not adapter.is_file():
        raise RefusedError(
            f"orch start refuses --role worker: no session adapter at {adapter}. "
            f"A worker starts only through the session adapter: {usage}"
        )
    if ask.folder is None:
        raise RefusedError(
            "orch start refuses --role worker without --dir: name the folder the worker "
            f"works in, as in {usage}"
        )
    if ask.vendor not in ADAPTER_VENDORS:
        raise RefusedError(
            f"orch start refuses --vendor {ask.vendor} for a worker: the session adapter "
            f"starts {' and '.join(ADAPTER_VENDORS)} only"
        )
    argv = [str(adapter), "start", ask.name, "--dir", str(ask.folder)]
    argv += ["--codex"] if ask.vendor == "codex" else []
    argv += ["--prompt", ask.prompt] if ask.prompt else []
    return Plan(argv, True, "")


def plan(ask: Request, repo: Path, store_root: Path | None, live: list[str]) -> Plan:
    if ask.role.strip().casefold() == ORCHESTRATOR and live:
        shown = ", ".join(session[:8] for session in live)
        raise RefusedError(
            f"orch start refuses --role {ORCHESTRATOR}: a live Orchestrator session holds "
            f"that role ({shown}); send the request to it instead of starting a second one"
        )
    if ask.role.strip() == WORKER:
        return _worker(ask, store_root)
    argv = launch(ask.vendor, ask.role, ask.name, repo)
    return Plan(argv, False, PRINTED.format(vendor=ask.vendor, role=ask.role))
