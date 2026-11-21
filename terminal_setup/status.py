from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import prerequisites, release_install, windows_node, windows_tools

_VERSION = re.compile(r"\d+(?:\.\d+)+")
_DATED = re.compile(r"\b(\d{8})-(\d{6})-[0-9a-f]+\b")
_WEZTERM_REPO = "wezterm/wezterm"
_UV_REPO = "astral-sh/uv"
APT_TOOLS = ("zsh", "tmux", "git", "tree")
RUNTIMES = ("python", "python3")
NODE = "node"


OPTIONAL_TOOLS = frozenset({"herdr"})
MANAGED = "managed"


@dataclass(frozen=True)
class Installed:
    command: str
    path: str
    version: str
    managed: bool = False


@dataclass(frozen=True)
class Row:
    command: str
    installed: str
    latest: str
    state: str


@dataclass(frozen=True)
class Lookups:
    release: Callable[[str], str] = release_install.latest_tag
    node: Callable[[str], str] = windows_node.latest_version


def release_repos() -> dict[str, str]:
    repos = {binary: repo for repo, binary, _ in prerequisites.RELEASE_TOOLS.values()}
    for tool in (*windows_tools.WINDOWS_TOOLS, windows_tools.STARSHIP):
        repos.setdefault(tool.command, tool.repo)
    repos.setdefault(prerequisites.STARSHIP_RELEASE[1], prerequisites.STARSHIP_RELEASE[0])
    repos.setdefault(prerequisites.HERDR_RELEASE[1], prerequisites.HERDR_RELEASE[0])
    repos.setdefault("wezterm", _WEZTERM_REPO)
    repos.setdefault("uv", _UV_REPO)
    return repos


def version_of(text: str) -> str:
    dated = _DATED.search(text or "")
    if dated:
        return dated.group()
    found = _VERSION.search(text or "")
    return found.group() if found else ""


def _numbers(version: str) -> tuple[int, ...]:
    dated = _DATED.fullmatch(version)
    if dated:
        return (int(dated.group(1)), int(dated.group(2)))
    return tuple(int(part) for part in version.split("."))


def _is_newer_dated(installed: str, latest: str) -> bool:
    if not _DATED.fullmatch(installed) or not _DATED.fullmatch(latest):
        return False
    return _numbers(installed) > _numbers(latest)


def state(installed: Installed | None, latest: str) -> str:
    if installed is None or not installed.path:
        return "missing"
    if not latest:
        return "unknown"
    current = version_of(installed.version)
    newest = version_of(latest)
    if not newest or not current:
        return "unknown"
    return "ok" if _numbers(current) >= _numbers(newest) else "update"


def _lookup(fetch: Callable[[str], str], key: str) -> str:
    try:
        return fetch(key)
    except OSError, ValueError, release_install.InstallError:
        return ""


def latest_versions(commands: Iterable[str], lookups: Lookups) -> dict[str, str]:
    repos = release_repos()
    wanted = sorted({repos[command] for command in commands if command in repos})
    with ThreadPoolExecutor(max_workers=8) as pool:
        tags = dict(
            zip(wanted, pool.map(lambda repo: _lookup(lookups.release, repo), wanted), strict=True)
        )
    latest = {command: tags[repos[command]] for command in commands if command in repos}
    if NODE in commands:
        latest[NODE] = _lookup(lookups.node, prerequisites.TARGET_NODE_MAJOR)
    for runtime in RUNTIMES:
        if runtime in commands:
            latest[runtime] = prerequisites.TARGET_PYTHON_MINOR
    return latest


def runtime_state(installed: Installed | None) -> str:
    if installed is None or not installed.path:
        return "missing"
    return "ok" if prerequisites.python_meets_target(installed.version) else "update"


def apt_candidates(policy: str) -> dict[str, str]:
    candidates: dict[str, str] = {}
    package = ""
    for line in policy.splitlines():
        if line and not line[0].isspace() and line.endswith(":"):
            package = line[:-1]
        elif package and line.strip().startswith("Candidate:"):
            value = line.split(":", 1)[1].strip()
            candidates[package] = "" if value == "(none)" else value
    return candidates


def rows(
    items: Iterable[Installed | None],
    commands: Iterable[str],
    latest: Mapping[str, str],
    unversioned: frozenset[str] = frozenset(),
) -> list[Row]:
    found = {item.command: item for item in items if item is not None}
    result = []
    for command in commands:
        item = found.get(command)
        newest = latest.get(command, "")
        installed = (version_of(item.version) or "present") if item and item.path else "-"
        if command in unversioned:
            result.append(Row(command, installed, "-", "ok" if item and item.path else "missing"))
            continue
        now = state(item, newest) if command not in RUNTIMES else runtime_state(item)
        if item is not None and item.managed and now != "missing":
            now = MANAGED
        shown = version_of(newest) or newest or "?"
        if now == "ok" and _is_newer_dated(installed, shown):
            shown = "nightly"
        result.append(Row(command, installed, shown, now))
    return result


def table(side: str, table_rows: Iterable[Row]) -> list[str]:
    listed = list(table_rows)
    tool = max([4, *(len(row.command) for row in listed)])
    have = max([9, *(len(row.installed) for row in listed)])
    newest = max([6, *(len(row.latest) for row in listed)])
    lines = [f"==> {side}", f"{'tool':<{tool}}  {'installed':<{have}}  {'latest':<{newest}}  state"]
    lines += [
        f"{row.command:<{tool}}  {row.installed:<{have}}  {row.latest:<{newest}}  {row.state}"
        for row in listed
    ]
    return lines


def plan_lines(side: str, table_rows: Iterable[Row]) -> list[str]:
    listed = list(table_rows)
    lines = [f"checked {side} {len(listed)}"]
    for row in listed:
        if row.command in APT_TOOLS and row.state == "update":
            lines.append(f"apt {side} {row.command}")
        elif row.state == "update" or (
            row.state == "missing" and row.command not in OPTIONAL_TOOLS
        ):
            lines.append(f"outdated {side} {row.command}")
    return lines
