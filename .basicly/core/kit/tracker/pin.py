from __future__ import annotations

from pathlib import Path

KIT_VERSION = "0.18.13"
PIN_FILE = ".kit-version"
INSTALL_SOURCE = (
    "git+https://github.com/niksavis/basicly@v{version}#subdirectory=packages/basicly-tracker"
)


class PinMismatchError(ValueError):
    pass


def pinned(directory: Path | str) -> str | None:

    path = Path(directory) / PIN_FILE
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def write(directory: Path | str) -> Path:

    path = Path(directory) / PIN_FILE
    path.write_text(f"{KIT_VERSION}\n", encoding="utf-8")
    return path


def require(directory: Path | str) -> None:

    held = pinned(directory)
    if held is None or held == KIT_VERSION:
        return
    source = INSTALL_SOURCE.format(version=held)
    raise PinMismatchError(
        f"this ledger pins tracker {held} and this tracker is {KIT_VERSION}; a tracker of "
        f"another version can drop event kinds it does not know, so nothing ran. Install the "
        f"pinned one with `uv tool install --force '{source}'`, or move the repository to "
        f"{KIT_VERSION} with `basicly-tracker update`"
    )
