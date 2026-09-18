from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
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


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not _CLI_ENTRY.is_file():
        print(
            f"markdownlint: skipped — {_CLI_ENTRY} is missing. Run `npm install` to "
            "enable the markdown gate (worktree provisioning does this for you)",
            file=sys.stderr,
        )
        return 0
    node = find_node()
    if node is None:
        print(
            "markdownlint: skipped — no usable node found on PATH, under nvm, or in "
            "/usr/bin. Install node (nvm install --lts) to enable the markdown gate; "
            "a Windows node reached through /mnt is deliberately not used",
            file=sys.stderr,
        )
        return 0
    return subprocess.run([str(node), str(_CLI_ENTRY), *args], check=False).returncode  # nosec B603


if __name__ == "__main__":
    sys.exit(main())
