from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any


def _merge_options(base: dict[str, Any], local: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in local.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge_options(result[key], value)
        else:
            result[key] = value
    return result


def _toml_value(value: object) -> str:
    if isinstance(value, dict):
        entries = (f"{json.dumps(key)} = {_toml_value(item)}" for key, item in value.items())
        return "{ " + ", ".join(entries) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, (str, bool, int, float)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    raise ValueError(f"Unsupported Starship override value type: {type(value).__name__}")


def _apply_local_overrides(home: Path, content: str) -> str:
    local = home / ".config" / "starship.local.toml"
    if not local.exists():
        return content
    settings = _merge_options(
        tomllib.loads(content), tomllib.loads(local.read_text(encoding="utf-8"))
    )
    return "".join(f"{json.dumps(key)} = {_toml_value(value)}\n" for key, value in settings.items())


def configure_zshenv(home: Path) -> None:
    destination = home / ".zshenv"
    content = destination.read_text(encoding="utf-8") if destination.exists() else ""
    setting = "skip_global_compinit=1"
    if setting in content.splitlines():
        return
    if destination.exists():
        shutil.copy2(destination, destination.with_name(".zshenv.terminal-setup.bak"))
    separator = "\n" if content and not content.endswith("\n") else ""
    destination.write_text(content + separator + setting + "\n", encoding="utf-8")


def write_starship_config(home: Path, source: Path, windows_starship: str | None) -> bool:
    content = source.read_text(encoding="utf-8")
    if windows_starship:
        section = "[git_status]\n"
        if content.count(section) != 1:
            raise ValueError("Starship template must contain exactly one [git_status] section")
        content = content.replace(
            section,
            section + f"windows_starship = {json.dumps(windows_starship, ensure_ascii=False)}\n",
        )
    destination = home / ".config" / "starship.toml"
    content = _apply_local_overrides(home, content)
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup = destination.exists() and destination.read_text(encoding="utf-8") != content
    if backup:
        shutil.copy2(destination, destination.with_name("starship.toml.terminal-setup.bak"))
    destination.write_text(content, encoding="utf-8")
    return backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--starship-template", type=Path)
    parser.add_argument("--wsl", action="store_true")
    parser.add_argument("--zsh", action="store_true")
    args = parser.parse_args()
    if args.zsh:
        configure_zshenv(args.home)
    if args.starship_template:
        bridge = shutil.which("starship.exe") if args.wsl else None
        if write_starship_config(args.home, args.starship_template, bridge):
            print(
                "Kept the old ~/.config/starship.toml as ~/.config/starship.toml.terminal-setup.bak"
            )


if __name__ == "__main__":
    main()
