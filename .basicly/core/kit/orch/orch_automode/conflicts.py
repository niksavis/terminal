from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from orch_automode import render

BASH = re.compile(r"^Bash\((?P<body>.*)\)$", re.DOTALL)
PROJECT_FILES = (".claude/settings.json", ".claude/settings.local.json")


@dataclass(frozen=True)
class Conflict:
    rule: str
    command: str
    pattern: str
    kind: str
    source: Path

    def line(self) -> str:
        effect = "blocks it before the classifier" if self.kind == "deny" else "forces a prompt"
        return (
            f"conflict: rule '{self.rule}' runs `{self.command}`, but {self.kind} pattern "
            f"{self.pattern} in {self.source} {effect}. Remove that pattern, or add "
            f'"{self.rule}" to omit in the automode config'
        )


def compile_pattern(body: str) -> re.Pattern[str]:
    if body.endswith(":*"):
        return re.compile(re.escape(body[:-2]) + ".*", re.DOTALL)
    tail = ""
    if body.endswith(" *"):
        body, tail = body[:-2], "(?: .*)?"
    return re.compile(".*".join(re.escape(part) for part in body.split("*")) + tail, re.DOTALL)


def patterns(path: Path) -> list[tuple[str, str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, UnicodeDecodeError, json.JSONDecodeError:
        return []
    rules = data.get("permissions") if isinstance(data, dict) else None
    if not isinstance(rules, dict):
        return []
    return [
        (kind, entry)
        for kind in ("deny", "ask")
        for entry in rules.get(kind, [])
        if isinstance(entry, str) and BASH.match(entry)
    ]


def commands(project: str, tag: str) -> list[tuple[str, str]]:
    source = render.rules()
    guarded = " ".join(source["guarded_paths"])  # type: ignore[arg-type]
    values = {f"<{key}>": value for key, value in source["sample"].items()}  # type: ignore[union-attr]
    values["<project>"] = project
    values["<tag>"] = (
        (tag or "v<version>")
        .replace("<name>", values["<name>"])
        .replace("<version>", values["<version>"])
    )
    found: list[tuple[str, str]] = []
    for kind in render.LISTS:
        for rule in source[kind]:
            lines = list(rule.get("examples", []))  # type: ignore[call-overload]
            lines += [render.shape(entry, guarded) for entry in rule.get("shapes", [])]  # type: ignore[attr-defined]
            for line in lines:
                filled = line
                for key, value in values.items():
                    filled = filled.replace(key, value)
                found += [(str(rule["name"]), part.strip()) for part in filled.split(render.SPLIT)]
    return found


def find(config: render.Config, settings: Path) -> list[Conflict]:
    workspace = Path(config.workspace).expanduser()
    out: list[Conflict] = []
    for project in config.projects:
        sources = [settings, *(workspace / project.name / name for name in PROJECT_FILES)]
        rules = [(kind, entry, path) for path in sources for kind, entry in patterns(path)]
        for rule, command in commands(project.name, project.tag):
            if rule in config.omit:
                continue
            for kind, entry, path in rules:
                body = BASH.match(entry)["body"]  # type: ignore[index]
                if compile_pattern(body).fullmatch(command):
                    out.append(Conflict(rule, command, entry, kind, path))
    return list(dict.fromkeys(out))
