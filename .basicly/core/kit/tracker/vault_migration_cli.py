from __future__ import annotations

import argparse
import getpass
import importlib.util
import json
import platform
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _load(name: str) -> Any:
    key = "basicly_tracker_kit_" + name
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, Path(__file__).with_name(name + ".py"))
    if spec is None or spec.loader is None:
        raise ImportError(name + ".py is missing from beside vault_migration_cli.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


migrate = _load("vault_migrate")
config = _load("vault_config")
git_runner = _load("git_runner")
vault_personal = _load("vault_personal")
ledger_freeze = _load("ledger_freeze")


def add_parser(sub: Any) -> None:
    form = sub.add_parser("migrate", help="import a backlog into a vault or export one prefix")
    form.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="the source ledger or export destination; default: current directory",
    )
    direction = form.add_mutually_exclusive_group(required=True)
    direction.add_argument("--to-vault", action="store_true")
    direction.add_argument("--from-vault", action="store_true")
    form.add_argument(
        "--preview", action="store_true", help="check a source without fetching or publishing"
    )
    form.add_argument(
        "--from", dest="source_format", choices=("ledger", "beads", "br", "beans"), default="ledger"
    )
    form.add_argument("--source", help="the source export or beans folder")
    form.add_argument("--vault", help="the vault URL or local repository")
    form.add_argument("--state", help="the private machine state folder")
    form.add_argument("--prefix", help="the prefix to export")
    form.add_argument(
        "--freeze",
        action="store_true",
        help="verify an imported local ledger, preserve its archive and switch to the vault",
    )
    form.add_argument(
        "--redact-name",
        action="append",
        default=[],
        help="replace this exact name with contributor; repeat for each name",
    )
    retention = form.add_mutually_exclusive_group()
    retention.add_argument(
        "--private-map", type=Path, help="an explicit private file for old and new event ids"
    )
    retention.add_argument(
        "--no-map-kept",
        action="store_true",
        help="keep no mapping; old external event references cannot be resolved",
    )
    form.add_argument(
        "--overwrite-private-map", action="store_true", help="replace an existing private map file"
    )


def _git_value(key: str, cwd: Path) -> str:
    try:
        return git_runner.run(["config", "--get", key], cwd).strip()
    except git_runner.GitRunnerError, git_runner.GitValueError, OSError:
        return ""


def _login() -> str:
    try:
        return getpass.getuser()
    except KeyError, OSError:
        return ""


def _repository(source: Path) -> Path:
    folder = source if source.is_dir() else source.parent
    return folder if folder.exists() else Path.cwd()


def identity(cwd: Path) -> dict[str, str]:
    name, email = _git_value("user.name", cwd), _git_value("user.email", cwd)
    if not name.strip() or not email.strip():
        raise ValueError(
            "git user.name or user.email does not resolve in "
            "the source repository, so migrate cannot redact them; "
            "set both with git config user.name and git config user.email, then preview again"
        )
    host = platform.node().split(".")[0]
    found = {
        "name and email": f"{name} <{email}>",
        "email": email,
        "name": name,
        "login": _login(),
        "host": host,
        "home": str(Path.home()),
    }
    short = {"login", "host"}
    return {
        label: value
        for label, value in found.items()
        if value.strip()
        and (label not in short or len(value) >= vault_personal.MIN_IDENTITY_LENGTH)
    }


HANDLE = r"(?<!github\.com/)(?<!github\.com:)"
HOME_FORM = re.compile(r"(?<![\w.-])[/\\]?(?:home|Users)[/\\](?!contributor\b)[A-Za-z0-9._-]+")
HOME_MARKER = "<redacted:home-path>"
STACKED = re.compile(r"(?:<redacted:[a-z][a-z0-9-]*>){2,}")


def _one_marker(found: re.Match[str]) -> str:
    text = found.group(0)
    return HOME_MARKER if "home-path>" in text else text[: text.index(">") + 1]


def _bounded(value: str, label: str = "") -> re.Pattern[str]:
    keep = HANDLE if label == "login" else ""
    return re.compile(keep + r"(?<!\w)" + re.escape(value) + r"(?!\w)")


def scanner(found: dict[str, str]) -> Callable[[Any], dict[str, int]]:
    patterns = {label: _bounded(value, label) for label, value in found.items()}

    def scan(lines: Any) -> dict[str, int]:
        text = vault_personal.decoded(lines)
        found = {label: len(pattern.findall(text)) for label, pattern in patterns.items()}
        found["other email"] = vault_personal.count_emails(text)
        if "home" in found:
            found["home"] += len(HOME_FORM.findall(text))
        return found

    return scan


def _redactor(
    args: argparse.Namespace,
    inherited: Callable[[str], str] | None,
    defaults: dict[str, str] | None = None,
) -> Callable[[str], str]:
    login = (defaults or {}).get("login", "")
    chosen = [
        *args.redact_name,
        *(v for k, v in (defaults or {}).items() if k not in {"home", "login"}),
    ]
    names = sorted(set(chosen), key=lambda value: (-len(value), value))
    if any(not name.strip() for name in names):
        raise ValueError("--redact-name is empty; supply a name or omit the option")
    pattern = (
        re.compile(r"(?<!\w)(?:" + "|".join(re.escape(name) for name in names) + r")(?!\w)")
        if names
        else None
    )

    own = _bounded(login, "login") if login.strip() else None

    def apply(value: str) -> str:
        text = vault_personal.redact_emails(value if inherited is None else inherited(value))
        text = STACKED.sub(_one_marker, HOME_FORM.sub(HOME_MARKER, text))
        text = text if pattern is None else pattern.sub("contributor", text)
        return text if own is None else own.sub("contributor", text)

    return apply


def _source(args: argparse.Namespace) -> tuple[list, dict[str, object]]:
    if args.source_format == "ledger":
        ledger = Path(args.source or args.directory)
        return migrate.ledger_events(ledger), migrate.templates.read(ledger)
    if not args.source:
        raise ValueError("--source is required for --from beads, br or beans")
    source = migrate.beans.Source(args.source_format, Path(args.source), "migration")
    return migrate.backlog_events(source), {}


def _clone(args: argparse.Namespace, state_root: Path | None) -> Any:
    held = config.load(Path.cwd()) if not args.vault else None
    vault = args.vault or (held.vault if held is not None else "")
    if not vault:
        raise ValueError("migration needs --vault URL or a project vault setting")
    state = Path(args.state) if args.state else state_root
    if state is None:
        raise ValueError("migration needs a machine state folder; supply --state DIRECTORY")
    return migrate.vault_clone.locate(state, vault)


def run(
    args: argparse.Namespace,
    inherited: Callable[[str], str] | None,
    clock: Callable[[], float],
    state_root: Path | None,
) -> dict[str, object]:
    if getattr(args, "freeze", False):
        return _freeze(args, inherited, clock, state_root)
    if args.from_vault:
        if (
            args.source
            or args.source_format != "ledger"
            or args.private_map
            or args.redact_name
            or args.overwrite_private_map
        ):
            raise ValueError(
                "export reads canonical data; use --from-vault TARGET --prefix NAME --vault URL"
            )
        if args.preview:
            raise ValueError("--preview checks a local source; use --to-vault --preview")
        if not args.prefix:
            raise ValueError("--from-vault requires --prefix NAME")
        return migrate.from_vault(
            _clone(args, state_root), args.prefix, Path(args.directory), clock=clock
        )
    if args.overwrite_private_map and args.private_map is None:
        raise ValueError("--overwrite-private-map requires --private-map FILE")
    found, template = _source(args)
    personal = identity(_repository(Path(args.source or args.directory).resolve()))
    rule = _redactor(args, inherited, personal)
    scan = scanner(personal)
    if args.preview:
        prepared = migrate.prepare(found, template, rule, redact_holders=True)
        shown = migrate.view_events(prepared.lines, migrate.EVERY_PROJECT)
        return {
            "preview": True,
            "personal_data": scan(prepared.lines),
            "records": len({event.record for event in found}),
            "events": len(found),
            "canonical_events": len(prepared.result.events),
            "reminted": prepared.result.reminted,
            "touched_fields": list(prepared.result.touched),
            "digest": migrate.digest(shown, {event.record for event in found}),
            "mapping": "not-kept",
            "external_citations": migrate.vault_citations.census(
                Path.cwd(),
                {row["old"] for row in prepared.result.mapping if row["old"] != row["new"]},
            ),
        }
    if args.private_map is None and not args.no_map_kept:
        raise ValueError("choose --private-map FILE or --no-map-kept before importing")
    plan = migrate.Import(
        _clone(args, state_root),
        clock,
        True,
        scan,
        rule,
        args.private_map,
        args.overwrite_private_map,
        code=Path.cwd(),
    )
    return migrate.to_vault(found, plan, template=template)


def _identity(event: Any) -> dict[str, object]:
    row = json.loads(migrate.events.to_json(event))
    return {key: row[key] for key in ("id", "record", "kind", "actor", "ts", "payload")}


def _freeze(
    args: argparse.Namespace,
    inherited: Callable[[str], str] | None,
    clock: Callable[[], float],
    state_root: Path | None,
) -> dict[str, object]:
    if not args.to_vault or args.preview or args.source_format != "ledger" or args.source:
        raise ValueError("--freeze needs migrate LEDGER --to-vault after importing that ledger")
    if args.private_map or args.overwrite_private_map:
        raise ValueError("--freeze creates no private mapping; run the import separately")
    if not args.prefix:
        raise ValueError("--freeze requires --prefix NAME for the project's imported records")
    migrate.vault_view.ids.validate_prefix(args.prefix)
    ledger = Path(args.directory).resolve()
    archive = ledger.with_name(ledger_freeze.ARCHIVE)
    source = (
        ledger_freeze.check(ledger)
        if ledger.is_file()
        else archive
        if not ledger.exists() and archive.exists()
        else ledger
    )
    expected = ledger_freeze.fingerprint(source)
    found = migrate.ledger_events(source)
    template = migrate.templates.read(source)
    if any(event.record.partition("-")[0] != args.prefix for event in found):
        raise ValueError("--prefix must name every record in the source ledger before freezing")
    if ledger_freeze.fingerprint(source) != expected:
        raise ValueError(
            "source history changed during freeze preflight; stop writers and try again"
        )
    personal = identity(_repository(ledger))
    prepared = migrate.prepare(
        found, template, _redactor(args, inherited, personal), redact_holders=True
    )
    clone = _clone(args, state_root)
    migrate.vault_clone.fetch(clone, clock=clock)
    valid = migrate.vault_clone.valid_events(clone)
    if migrate.vault_template.carried(valid, args.prefix) != migrate.vault_template.carried(
        prepared.lines, args.prefix
    ):
        raise ValueError(
            "the source template differs from its vault import; "
            "restore the verified source template before retrying --freeze"
        )
    want = migrate.vault_view.Want(args.prefix)
    migrate.canonical.check(migrate.view_events(valid, want))
    held = {event.id: _identity(event) for event in migrate.vault_view.carried(valid, want)}
    if any(held.get(event.id) != _identity(event) for event in prepared.result.events):
        raise ValueError(
            "source events do not match the vault import; "
            "run migrate --to-vault with the same redaction first"
        )
    existing = config.load(ledger.parent.parent)
    vault = args.vault or (existing.vault if existing is not None else "")
    if existing is not None:
        if migrate.vault_clone.vault_source(existing.vault)[0] != clone.url:
            raise ValueError("the repository already names a different vault; nothing was frozen")
        vault = existing.vault
    report = ledger_freeze.freeze(ledger, vault, args.prefix, expected)
    return {**report, "records": len({event.record for event in found}), "events": len(found)}
