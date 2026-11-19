from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

CONFIG_PATH = Path(".basicly-tracker.toml")
KEYS = ("vault", "prefix")
_LINE = re.compile(r'^\s*([a-z_]+)\s*=\s*"([^"\\]*)"\s*(?:#.*)?$')
_PREFIX = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    path: Path
    vault: str
    prefix: str


def find(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        candidate = folder / CONFIG_PATH
        if candidate.is_file():
            return candidate
        if (folder / ".git").exists():
            return None
    return None


def parse(path: Path) -> Config:
    found: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if match is None or match.group(1) not in KEYS:
            raise ConfigError(
                f'{path}:{number}: write each setting as key = "value" with key vault or prefix'
            )
        found[match.group(1)] = match.group(2)
    missing = [key for key in KEYS if not found.get(key)]
    if missing:
        raise ConfigError(f'{path}: set {" and ".join(missing)}, as in vault = "URL"')
    if not _PREFIX.match(found["prefix"]):
        raise ConfigError(f"{path}: prefix {found['prefix']!r} must be lowercase, like basicly")
    return Config(path, found["vault"], found["prefix"])


def load(start: Path) -> Config | None:
    path = find(start)
    return None if path is None else parse(path)


def address(vault: str) -> str:
    if "\\" in vault and PureWindowsPath(vault).is_absolute():
        vault = PureWindowsPath(vault).as_posix()
    if not vault or not vault.isprintable() or '"' in vault or "\\" in vault:
        raise ConfigError("vault must be a printable Git address using forward slashes")
    return vault


def text(vault: str, prefix: str) -> str:
    vault = address(vault)
    if not _PREFIX.fullmatch(prefix):
        raise ConfigError("prefix must be lowercase, like basicly")
    return f'vault = "{vault}"\nprefix = "{prefix}"\n'


def with_vault(argv: list, start: Path, verbs: frozenset) -> list:
    if not argv or argv[0] not in verbs or "--vault" in argv:
        return argv
    config = load(start)
    return argv if config is None else [*argv, "--vault", config.vault]
