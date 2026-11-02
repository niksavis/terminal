from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
import tomllib
from pathlib import Path, PurePath

_CLI_ENTRY = Path("node_modules") / "markdownlint-cli2" / "markdownlint-cli2-bin.mjs"

_NVM_ROOTS = ("versions/node",)
_SYSTEM_NODES = (Path("/usr/local/bin/node"), Path("/usr/bin/node"))


def _is_windows_interop(candidate: PurePath) -> bool:

    posix = candidate.as_posix()
    return sys.platform == "linux" and (posix == "/mnt" or posix.startswith("/mnt/"))


def _version_key(directory: Path) -> tuple[int, ...]:

    parts = directory.name.lstrip("v").split(".")
    return tuple(int(part) if part.isdigit() else 0 for part in parts)


def _nvm_nodes() -> list[Path]:
    nvm_dir = Path(os.environ.get("NVM_DIR") or Path.home() / ".nvm")
    found: list[Path] = []
    for relative in _NVM_ROOTS:
        root = nvm_dir / relative
        if not root.is_dir():
            continue
        found += sorted((d for d in root.iterdir() if d.is_dir()), key=_version_key, reverse=True)
    return [d / "bin" / "node" for d in found]


def find_node() -> Path | None:

    on_path = shutil.which("node")
    if on_path and not _is_windows_interop(Path(on_path)):
        return Path(on_path)
    for candidate in (*_nvm_nodes(), *_SYSTEM_NODES):
        if candidate.is_file() and not _is_windows_interop(candidate):
            return candidate
    return None


def markdownlint_enabled(repo_root: Path) -> bool:
    enabled = True
    for path in (
        repo_root / "basicly.toml",
        *sorted((repo_root / "basicly.d").glob("*.toml")),
        repo_root / "basicly.local.toml",
    ):
        if not path.exists():
            continue
        try:
            document = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(
                f"{path.name}: cannot read markdownlint configuration: {error}"
            ) from error
        section = document.get("hooks", {})
        if not isinstance(section, dict):
            raise ValueError(f"{path.name}: hooks must be a table")
        settings = section.get("markdownlint", {})
        if not isinstance(settings, dict):
            raise ValueError(f"{path.name}: hooks.markdownlint must be a table")
        unknown = set(settings) - {"enabled"}
        if unknown:
            raise ValueError(
                f"{path.name}: unknown hooks.markdownlint setting(s): {', '.join(sorted(unknown))}"
            )
        if "enabled" in settings:
            enabled = settings["enabled"]
            if not isinstance(enabled, bool):
                raise ValueError(f"{path.name}: hooks.markdownlint.enabled must be true or false")
    return enabled


def prerequisites(repo_root: Path) -> Path | None:
    if not markdownlint_enabled(repo_root):
        print("markdownlint: opted out by hooks.markdownlint.enabled=false")
        return None
    if not (repo_root / _CLI_ENTRY).is_file():
        raise ValueError(
            f"{_CLI_ENTRY} is missing. With approval, run "
            "`npm install --save-dev markdownlint-cli2` and commit the package files; "
            "if it is already declared and locked, run `npm ci`. "
            "To opt out explicitly, set [hooks.markdownlint] enabled=false in basicly.toml"
        )
    node = find_node()
    remedy = (
        "no usable node found on PATH, under nvm, or in /usr/bin. "
        "Install Node with `nvm install --lts`; "
        "a Windows node reached through /mnt is deliberately not used"
    )
    if node is None:
        raise ValueError(remedy)
    try:
        version = subprocess.run(  # nosec B603
            [str(node), "--version"], capture_output=True, check=False
        )
    except OSError as error:
        raise ValueError(remedy) from error
    if version.returncode != 0:
        raise ValueError(remedy)
    return node


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    try:
        node = prerequisites(Path.cwd())
        if node is None or args == ["--check-prerequisites"]:
            return 0
        return subprocess.run([str(node), str(_CLI_ENTRY), *args], check=False).returncode  # nosec B603
    except (OSError, ValueError) as error:
        print(f"markdownlint: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
