from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path, PurePath, PureWindowsPath


def resolve_command(command: Sequence[str], repo_root: PurePath) -> list[str]:
    if not command:
        raise ValueError("a check command must name an executable")
    program = command[0]
    windows = isinstance(repo_root, PureWindowsPath)
    path = PureWindowsPath(program) if windows else PurePath(program)
    if windows and path.drive and not path.is_absolute():
        raise ValueError("drive-relative executables are ambiguous; use a fully qualified path")
    separators = ("/", "\\") if windows else ("/",)
    if not path.is_absolute() and any(separator in program for separator in separators):
        root = repo_root.resolve() if isinstance(repo_root, Path) else repo_root
        return [str(root / path), *command[1:]]
    return list(command)
