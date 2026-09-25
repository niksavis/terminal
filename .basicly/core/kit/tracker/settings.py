from __future__ import annotations

import importlib.util
import json
import shlex
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside settings.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


templates = _load("templates.py", "basicly_tracker_kit_templates")
holders = _load("holders.py", "basicly_tracker_kit_holders")
pin = _load("pin.py", "basicly_tracker_kit_pin")
install_hook = _load("install_hook.py", "basicly_tracker_kit_install_hook")
events = holders.events
ids = events.ids

LEDGER_FILE = "ledger file"
DEFAULT_SOURCE = "default"
FOLD_SOURCE = f"git hook {install_hook.HOOK_NAME}"
TEMPLATE_HOME = f"{templates.TEMPLATE_FILE} in the ledger"
UPDATE = "basicly-tracker update"


class SettingError(ValueError):
    pass


def _json(raw: str) -> object:

    try:
        return json.loads(raw)
    except ValueError as exc:
        raise SettingError(f"{raw!r} is not a JSON value: {exc}") from exc


_IN_TEMPLATE: dict[str, Callable[[str], object]] = {
    "mode": str,
    "prefix": ids.validate_prefix,
    "sections": _json,
    "stale_days": _json,
    "types": _json,
}

_ELSEWHERE: dict[str, tuple[str, Callable[[str], str]]] = {
    "fold_on_merge": (
        "the post-merge git hook",
        lambda value: f"{UPDATE} --fold-on-merge" if value.lower() == "true" else UPDATE,
    ),
    "holder": (
        holders.HOLDER_GIT_CONFIG,
        lambda value: f"{holders.HOLDER_GIT_CONFIG} {shlex.quote(value)}",
    ),
    "pin": (f"{pin.PIN_FILE} in the ledger", lambda _value: UPDATE),
}

NAMES = tuple(sorted({*_IN_TEMPLATE, *_ELSEWHERE}))


def _repository_root(ledger: Path) -> Path | None:

    resolved = ledger.resolve()
    return next(
        (one for one in (resolved, *resolved.parents) if install_hook.git_dir(one) is not None),
        None,
    )


def _folds_on_merge(ledger: Path) -> bool:

    root = _repository_root(ledger)
    hooks = install_hook.hooks_dir(root) if root is not None else None
    hook = hooks / install_hook.HOOK_NAME if hooks is not None else None
    return hook is not None and hook.is_file() and install_hook.BEGIN in hook.read_text("utf-8")


def _template_values(template: Any) -> dict[str, object]:
    return {
        "mode": template.mode,
        "prefix": template.prefix or None,
        "sections": list(template.sections),
        "stale_days": template.stale_days,
        "types": {kind: list(headings) for kind, headings in template.types},
    }


def _row(name: str, value: object, source: str, home: str) -> dict[str, object]:
    return {"name": name, "value": value, "source": source, "home": home}


def report(
    directory: Path | str, *, start: Path, environ: Mapping[str, str] | None = None
) -> dict[str, object]:

    ledger = Path(directory)
    held = templates.read(ledger)
    template = templates.parse(held, ledger / templates.TEMPLATE_FILE)
    rows = [
        _row(name, value, LEDGER_FILE if name in held else DEFAULT_SOURCE, TEMPLATE_HOME)
        for name, value in _template_values(template).items()
    ]
    holder, source = holders.holder_and_source(start, environ)
    folds = _folds_on_merge(ledger)
    pinned = pin.pinned(ledger)
    rows += [
        _row("holder", holder or None, source, _ELSEWHERE["holder"][0]),
        _row(
            "fold_on_merge",
            folds,
            FOLD_SOURCE if folds else DEFAULT_SOURCE,
            _ELSEWHERE["fold_on_merge"][0],
        ),
        _row("pin", pinned, LEDGER_FILE if pinned else DEFAULT_SOURCE, _ELSEWHERE["pin"][0]),
    ]
    return {"settings": sorted(rows, key=lambda row: str(row["name"]))}


def write(directory: Path | str, name: str, raw: str) -> dict[str, object]:

    if name in _ELSEWHERE:
        home, command = _ELSEWHERE[name]
        raise SettingError(
            f"{name} lives in {home}, which config does not write; set it with `{command(raw)}`"
        )
    decode = _IN_TEMPLATE.get(name)
    if decode is None:
        raise SettingError(f"no setting is named {name!r}; the settings are {', '.join(NAMES)}")
    value = decode(raw)
    ledger = Path(directory)
    path = ledger / templates.TEMPLATE_FILE
    with events.LedgerLock(ledger):
        updated = {**templates.read(ledger), name: value}
        templates.parse(updated, path)
        temporary = events.temporary_beside(path)
        text = json.dumps(updated, indent=2, sort_keys=True, ensure_ascii=False)
        temporary.write_text(f"{text}\n", encoding="utf-8")
        events.replace_file(temporary, path)
    return {"set": {"name": name, "value": value, "source": LEDGER_FILE}}


def create_prefix(directory: Path | str, given: str) -> str:

    chosen = given or templates.load(directory).prefix
    if not chosen:
        raise SettingError(
            f"create needs an id prefix and {directory} sets none: pass --prefix NAME, or "
            f"set it once for the ledger with `config {directory} set prefix NAME`"
        )
    return chosen
