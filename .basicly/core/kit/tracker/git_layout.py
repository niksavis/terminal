from __future__ import annotations

from pathlib import Path

GIT_DIR_NAME = ".git"
_GIT_DIR_MARK = "gitdir:"
DEFAULT_HOOKS_DIR = "hooks"
HOOKS_PATH_KEY = "hookspath"


def git_dir(root: Path) -> Path | None:

    candidate = root / GIT_DIR_NAME
    if candidate.is_dir():
        return candidate
    if candidate.is_file():
        text = candidate.read_text(encoding="utf-8").strip()
        if text.startswith(_GIT_DIR_MARK):
            linked = Path(text[len(_GIT_DIR_MARK) :].strip())
            return linked if linked.is_absolute() else (root / linked).resolve()
    return None


def hooks_dir(root: Path, override: Path | None = None) -> Path | None:

    if override is not None:
        return override
    found = git_dir(root)
    if found is None:
        return None
    common = found / "commondir"
    if common.is_file():
        found = (found / common.read_text(encoding="utf-8").strip()).resolve()
    config = found / "config"
    declared = ""
    if config.is_file():
        for line in config.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip().lower() == HOOKS_PATH_KEY:
                declared = value.strip()
    if not declared:
        return found / DEFAULT_HOOKS_DIR
    path = Path(declared)
    return path if path.is_absolute() else (root / path)


REDIRECT_FILE = "redirect"


class RedirectError(ValueError):
    pass


def _place(ledger: Path, checkout: Path | None) -> Path:

    if checkout is not None:
        return ledger.relative_to(checkout)
    here = ledger.resolve()
    home = next((one for one in here.parents if (one / GIT_DIR_NAME).exists()), None)
    if home is None:
        raise RedirectError(
            f"the ledger redirect {ledger / REDIRECT_FILE} sits outside a git checkout, so the "
            "place of the shared ledger it names is unknown and nothing ran"
        )
    return here.relative_to(home)


def _followed(ledger: Path, checkout: Path | None) -> tuple[Path, Path] | None:

    marker = ledger / REDIRECT_FILE
    if not marker.is_file():
        return None
    try:
        named = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RedirectError(f"the ledger redirect {marker} cannot be read: {exc}") from exc
    place = _place(ledger, checkout)
    if not named or not (Path(named) / place).is_dir():
        raise RedirectError(
            f"the ledger redirect {marker} names {named or 'no checkout'}, which holds no "
            f"{place.as_posix()}, so nothing ran; write the base checkout's path into "
            f"{marker}, or delete it to use this ledger"
        )
    return Path(named), place


def redirect_target(ledger: Path, checkout: Path) -> Path | None:

    followed = _followed(ledger, checkout)
    return followed[0] if followed else None


def shared_ledger(ledger: Path | str) -> Path:

    followed = _followed(Path(ledger), None)
    return Path(ledger) if followed is None else followed[0] / followed[1]
