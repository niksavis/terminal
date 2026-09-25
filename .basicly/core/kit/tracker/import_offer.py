from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent

BEADS = "beads"
BEANS = "beans"
SOURCES = (BEADS, BEANS)

BEADS_EXPORT = ".beads/issues.jsonl"
DOLT_STORES = (".beads/dolt", ".beads/embeddeddolt")
BD_EXPORT = f"bd export -o {BEADS_EXPORT}"
BEANS_CONFIG = ".beans.yml"
BEANS_DIR = ".beans"
BEANS_FOLDER = "<the beans folder>"

SEARCHED = {
    BEADS: f"{BEADS_EXPORT} and no bd Dolt store under .beads",
    BEANS: f"bean file under {BEANS_DIR} and no {BEANS_CONFIG}",
}

KIT_IMPORT = "python3 {cli} import {ledger} {path} --from {source}"
YES = frozenset({"y", "yes"})


class ImportOfferError(ValueError):
    pass


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside import_offer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Backlog:
    source: str
    path: str
    count: int
    owed: str = ""


@dataclass(frozen=True)
class Install:
    root: Path
    ledger: Path
    chosen: str = ""
    import_command: str = KIT_IMPORT
    dry_run: bool = False


def _shown(path: Path, root: Path) -> str:

    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _beads_backlog(root: Path) -> Backlog | None:

    export = root / BEADS_EXPORT
    if export.is_file():
        lines = export.read_text(encoding="utf-8").splitlines()
        return Backlog(BEADS, BEADS_EXPORT, sum(1 for line in lines if line.strip()))
    for store in DOLT_STORES:
        if (root / store).is_dir():
            owed = f"a bd Dolt store at {store} and no {BEADS_EXPORT}: run `{BD_EXPORT}` first"
            return Backlog(BEADS, BEADS_EXPORT, 0, owed)
    return None


def _beans_backlog(root: Path) -> Backlog | None:

    if (root / BEANS_DIR).is_dir():
        beans = _load("beans.py", "basicly_tracker_kit_beans")
        try:
            _folder, files = beans.bean_files(root)
        except beans.BeansFormError:
            files = []
        if files:
            return Backlog(BEANS, BEANS_DIR, len(files))
    if not (root / BEANS_CONFIG).is_file():
        return None
    owed = f"{BEANS_CONFIG} and no bean file under {BEANS_DIR}: name the folder it sets"
    return Backlog(BEANS, BEANS_FOLDER, 0, owed)


def find_backlogs(root: Path) -> tuple[Backlog, ...]:

    found = (_beads_backlog(root), _beans_backlog(root))
    return tuple(backlog for backlog in found if backlog is not None)


def chosen_backlogs(install: Install) -> tuple[Backlog, ...]:

    found = find_backlogs(install.root)
    named = next((one for one in found if one.source == install.chosen), None)
    if install.chosen and named is None:
        raise ImportOfferError(
            f"--import {install.chosen} names a {install.chosen} backlog, and "
            f"{install.root.name} holds no {SEARCHED[install.chosen]}; nothing was imported"
        )
    if named is not None and named.owed:
        raise ImportOfferError(
            f"--import {install.chosen} found {named.owed}, then run "
            f"`{_how_to_import(install, named)}`; nothing was imported"
        )
    return found


def _how_to_import(install: Install, backlog: Backlog) -> str:

    template = KIT_IMPORT if backlog.path == BEANS_FOLDER else install.import_command
    return template.format(
        cli=_shown(_HERE / "cli.py", install.root),
        ledger=_shown(install.ledger, install.root),
        path=backlog.path,
        source=backlog.source,
    )


def _refine_note(install: Install) -> str:

    cli = _shown(_HERE / "cli.py", install.root)
    ledger = _shown(install.ledger, install.root)
    return (
        "tracker: an imported open record lands in refine, not in ready: it has no Trigger, "
        "Acceptance Criteria or Requirements, so `ready` shows 0 until each one is shaped; "
        f"list them with `python3 {cli} refine {ledger}`\n"
    )


def _report(install: Install, backlog: Backlog, *, dry_run: bool) -> dict[str, Any]:

    migrate = _load("migrate.py", "basicly_tracker_kit_migrate")
    beans = _load("beans.py", "basicly_tracker_kit_beans")
    try:
        snapshot = beans.READERS[backlog.source](install.root / backlog.path)
    except migrate.SnapshotError as exc:
        raise ImportOfferError(f"the {backlog.source} backlog cannot be read: {exc}") from exc
    return migrate.import_report(install.ledger, snapshot, dry_run=dry_run)


def _refused(report: dict[str, Any], stream: Any) -> None:

    for one in report["rejected"]:
        stream.write(f"tracker:   refused {one['subject']}: {one['reason']}\n")


def _summary(install: Install, backlog: Backlog, report: dict[str, Any], stream: Any) -> None:

    verb = "a dry run would import" if report["dry_run"] else "imported"
    stream.write(
        f"tracker: {verb} {len(report['imported'])} record(s) from {backlog.path} into "
        f"{_shown(install.ledger, install.root)}; {len(report['rejected'])} refused\n"
    )
    _refused(report, stream)


def _planned(install: Install, backlog: Backlog) -> dict[str, Any] | None:

    return _report(install, backlog, dry_run=True) if install.ledger.is_dir() else None


def _answered_yes(ask: Callable[[str], str], backlog: Backlog) -> bool:

    try:
        answer = ask(f"tracker: import the {backlog.source} backlog now? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in YES


def _not_asked(install: Install) -> str:

    if install.dry_run:
        return "this is a dry run"
    if install.chosen:
        return f"--import named {install.chosen}"
    return "no terminal was there to answer"


def _offer_one(
    install: Install, backlog: Backlog, ask: Callable[[str], str] | None, stream: Any
) -> None:

    how = _how_to_import(install, backlog)
    if backlog.owed:
        stream.write(f"tracker: found {backlog.owed}, then run `{how}`\n")
        return
    noun = "bean(s)" if backlog.source == BEANS else "record(s)"
    found = f"{backlog.path} holds {backlog.count} {noun}"
    if install.chosen == backlog.source and not install.dry_run:
        stream.write(f"tracker: found a {backlog.source} backlog: {found}\n")
        _summary(install, backlog, _report(install, backlog, dry_run=False), stream)
        stream.write(_refine_note(install))
        return
    try:
        plan = _planned(install, backlog)
    except ImportOfferError as exc:
        stream.write(f"tracker: found {backlog.path}, but {exc}; nothing was imported\n")
        return
    if plan is not None and not plan["imported"]:
        stream.write(
            f"tracker: the {backlog.source} backlog at {backlog.path} is already in the ledger "
            f"({backlog.count} {noun})\n"
        )
        _refused(plan, stream)
        return
    stream.write(f"tracker: found a {backlog.source} backlog: {found}\n")
    if plan is not None:
        _summary(install, backlog, plan, stream)
    asking = None if install.dry_run or install.chosen else ask
    if asking is None:
        stream.write(
            f"tracker: nothing was imported, because {_not_asked(install)}; "
            f"to import it, run `{how}`\n"
        )
        stream.write(_refine_note(install))
        return
    if not _answered_yes(asking, backlog):
        stream.write(f"tracker: nothing was imported; to import it later, run `{how}`\n")
        return
    _summary(install, backlog, _report(install, backlog, dry_run=False), stream)
    stream.write(_refine_note(install))


def offer_import(
    install: Install,
    backlogs: tuple[Backlog, ...],
    *,
    ask: Callable[[str], str] | None,
    stream: Any,
) -> None:

    for backlog in backlogs:
        _offer_one(install, backlog, ask, stream)
