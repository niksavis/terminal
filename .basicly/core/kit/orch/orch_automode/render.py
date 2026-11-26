from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from orch_lessons.log import RefusedError

RULES = Path(__file__).with_name("rules.json")
DEFAULTS = "$defaults"
LISTS = ("allow", "soft_deny", "environment")
VISIBILITY = ("public", "private")
SPLIT = " && "
CLASSES = {
    "host": re.compile(r"[a-z0-9][a-z0-9.-]*"),
    "owner": re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*"),
    "name": re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*"),
    "workspace": re.compile(r"~?/[A-Za-z0-9._/-]*"),
    "tag": re.compile(r"(?:<name>--)?v<version>"),
    "label": re.compile(r"[A-Za-z0-9][A-Za-z0-9 ()'._-]*"),
}
LABEL = re.compile(r"^[\s*_`>-]*(?P<label>[^:*]+?)[\s*_`]*:")
CONFIG_HELP = (
    '{"host": "github.com", "owner": "<account>", "workspace": "~/development", '
    '"repositories": [{"name": "<repo>", "visibility": "public", "project": true, '
    '"tag": "v<version>"}], "omit": [], "drop": []}'
)


@dataclass(frozen=True)
class Repo:
    name: str
    visibility: str
    project: bool
    tag: str


@dataclass(frozen=True)
class Config:
    host: str
    owner: str
    workspace: str
    repos: tuple[Repo, ...]
    omit: frozenset[str]
    drop: frozenset[str] = frozenset()

    @property
    def projects(self) -> list[Repo]:
        return [repo for repo in self.repos if repo.project]


def _token(kind: str, value: object, where: str) -> str:
    if not isinstance(value, str) or not CLASSES[kind].fullmatch(value):
        raise RefusedError(
            f"automode config: {where} is {value!r}; it must match {CLASSES[kind].pattern}. "
            f"Write the config as: {CONFIG_HELP}"
        )
    return value


def _repo(entry: object, index: int) -> Repo:
    where = f"repositories[{index}]"
    if not isinstance(entry, dict):
        raise RefusedError(f"automode config: {where} is not an object; write it as {CONFIG_HELP}")
    visibility = entry.get("visibility")
    if visibility not in VISIBILITY:
        raise RefusedError(
            f"automode config: {where}.visibility is {visibility!r}; use public or private"
        )
    tag = entry.get("tag", "")
    return Repo(
        _token("name", entry.get("name"), f"{where}.name"),
        visibility,
        entry.get("project") is True,
        _token("tag", tag, f"{where}.tag") if tag else "",
    )


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RefusedError(
            f"automode config: cannot read {path} ({exc}); write it as {CONFIG_HELP}"
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("repositories"), list):
        raise RefusedError(
            f"automode config: {path} needs a repositories list; write it as {CONFIG_HELP}"
        )
    repos = tuple(_repo(entry, index) for index, entry in enumerate(data["repositories"]))
    if not any(repo.project for repo in repos):
        raise RefusedError(f"automode config: {path} names no repository with project true")
    omit = data.get("omit", [])
    names = {str(rule["name"]) for kind in LISTS for rule in rules()[kind]}
    if not isinstance(omit, list) or not set(omit) <= names - {"Shared Terms"}:
        raise RefusedError(
            f"automode config: omit must list rule names from {sorted(names - {'Shared Terms'})}"
        )
    drop = data.get("drop", [])
    if not isinstance(drop, list):
        raise RefusedError("automode config: drop must be a list of rule labels")
    labels = frozenset(
        _token("label", item, f"drop[{index}]").lower() for index, item in enumerate(drop)
    )
    return Config(
        _token("host", data.get("host"), "host"),
        _token("owner", data.get("owner"), "owner"),
        _token("workspace", data.get("workspace"), "workspace"),
        repos,
        frozenset(omit),
        labels,
    )


def rules() -> dict[str, list[dict[str, object]]]:
    return json.loads(RULES.read_text(encoding="utf-8"))


def _names(repos: list[Repo]) -> str:
    return ", ".join(f"{repo.name}" for repo in repos) or "none"


def shape(entry: dict[str, object], guarded: str) -> str:
    guards = [str(guard).replace("{guarded}", guarded) for guard in entry["guards"]]  # type: ignore[union-attr]
    return SPLIT.join([*guards, str(entry["action"])])


def guard_line(entry: dict[str, object], guarded: str, sentinel: str) -> str:
    guards = [str(guard).replace("{guarded}", guarded) for guard in entry["guards"]]  # type: ignore[union-attr]
    return SPLIT.join([*guards, sentinel])


def _fill(text: str, config: Config) -> str:
    tags = sorted({f"{repo.name}: {repo.tag}" for repo in config.projects if repo.tag})
    values = {
        "projects": _names(config.projects),
        "workspace": config.workspace,
        "host": config.host,
        "owner": config.owner,
        "public": _names([r for r in config.repos if r.visibility == "public"]),
        "private": _names([r for r in config.repos if r.visibility == "private"]),
        "repos": ", ".join(f"{config.owner}/{repo.name}" for repo in config.repos),
        "tags": "; ".join(tags) or "none",
    }
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def entries(config: Config) -> dict[str, list[str]]:
    source = rules()
    guarded = " ".join(source["guarded_paths"])  # type: ignore[arg-type]
    made: dict[str, list[str]] = {}
    for kind in LISTS:
        out = []
        for rule in source[kind]:
            if rule["name"] in config.omit:
                continue
            text = str(rule["text"])
            for entry in rule.get("shapes", []):  # type: ignore[attr-defined]
                text = text.replace("{shape}", shape(entry, guarded), 1)
            body = _fill(text, config)
            out.append(
                f"**{rule['name']}**: {body}"
                if kind == "environment"
                else f"{rule['name']}: {body}"
            )
        made[kind] = out
    return made


def label(entry: str) -> str:
    found = LABEL.match(entry)
    return re.sub(r"\s*\[.*$", "", found["label"]).strip().lower() if found else ""


def merge(
    document: dict[str, object], made: dict[str, list[str]], drop: frozenset[str] = frozenset()
) -> dict[str, object]:
    merged = dict(document)
    found = merged.get("autoMode")
    auto: dict[str, object] = dict(found) if isinstance(found, dict) else {}
    for kind in LISTS:
        owned = {label(entry) for entry in made[kind]} | drop
        existing = auto.get(kind)
        kept = [
            e
            for e in (existing if isinstance(existing, list) else [])
            if isinstance(e, str) and label(e) not in owned and e != DEFAULTS
        ]
        auto[kind] = [DEFAULTS, *kept, *made[kind]]
    merged["autoMode"] = auto
    return merged


def size(lists: dict[str, list[str]]) -> int:
    return sum(
        len(entry)
        for kind in ("allow", "soft_deny")
        for entry in lists.get(kind, [])
        if entry != DEFAULTS
    )
