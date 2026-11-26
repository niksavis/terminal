from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


def _load(file_name: str, module_name: str) -> Any:

    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, _HERE / file_name)
    if spec is None or spec.loader is None:
        raise ImportError(f"the tracker kit's {file_name} is missing from beside vault_cli.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


vault_shapes = _load("vault_shapes.py", "basicly_tracker_kit_vault_shapes")
vault_fold = _load("vault_fold.py", "basicly_tracker_kit_vault_fold")
vault_clone = _load("vault_clone.py", "basicly_tracker_kit_vault_clone")
vault_queue = _load("vault_queue.py", "basicly_tracker_kit_vault_queue")
vault_share = _load("vault_share.py", "basicly_tracker_kit_vault_share")
vault_repair = _load("vault_repair.py", "basicly_tracker_kit_vault_repair")
vault_hooks = _load("vault_hooks.py", "basicly_tracker_kit_vault_hooks")
vault_claim = _load("vault_claim.py", "basicly_tracker_kit_vault_claim")
vault_commit_hook = _load("vault_commit_hook.py", "basicly_tracker_kit_vault_commit_hook")
vault_config = _load("vault_config.py", "basicly_tracker_kit_vault_config")
vault_init = _load("vault_init.py", "basicly_tracker_kit_vault_init")
vault_push_hooks = _load("vault_push_hooks.py", "basicly_tracker_kit_vault_push_hooks")
vault_view = _load("vault_view.py", "basicly_tracker_kit_vault_view")
vault_write = _load("vault_write.py", "basicly_tracker_kit_vault_write")
ledger_freeze = _load("ledger_freeze.py", "basicly_tracker_kit_ledger_freeze")


def check_frozen() -> None:
    config = vault_config.load(Path.cwd())
    if config is not None:
        ledger_freeze.check(config.path.parent / ledger_freeze.LEDGER)
    else:
        root = _repository_root(Path.cwd()) or Path.cwd()
        ledger_freeze.check_source(root / ledger_freeze.LEDGER)


READS = frozenset({
    "commit-check",
    "list",
    "ready",
    "show",
    "blocked",
    "stats",
    "board",
    "refine",
    "refine-sheet",
    "dor",
    "fields",
    "scaffold",
})


def route_ledger_alias(args: argparse.Namespace) -> None:
    if args.command == "commit-check":
        config = vault_write.config_of(args.directory)
        if config is not None:
            harness_config(config.path.parent)
            args.command = "commit-msg-vault"
            args.vault = config.vault
            args.state = None
            args.session = None
        return
    if args.command not in {"claim", "unassign"}:
        return
    config = vault_write.config_of(args.directory)
    if config is None:
        return
    incompatible = ("to", "take") if args.command == "claim" else ("by",)
    if flag := next((name for name in incompatible if getattr(args, name, "")), ""):
        command = shlex.join([args.command, args.record])
        fix = (
            f"{args.command} {args.record} cannot translate --{flag} into the vault protocol; "
            f"run `{command}`"
        )
        raise vault_write.VaultRefusedError({"exit": 1, "record": args.record, "fix": fix})
    argv = [args.command, args.record, "--vault", config.vault]
    if args.command == "unassign" and args.take:
        argv.append("--take")
    forms = _load("vault_arguments.py", "basicly_tracker_kit_vault_arguments").FORMS
    args.__dict__.update(vars(forms[args.command]().parse_args(argv)))


def _vault_show(args: argparse.Namespace) -> dict[str, object]:
    found = vault_shapes.valid_events(vault_shapes.read(args.vault, args.ref))
    return vault_fold.view(vault_fold.fold(found).record(args.record))


def _state_root() -> Path:
    return vault_clone.state_root(os.environ, Path.home(), windows=os.name == "nt")


def _state(args: argparse.Namespace) -> Path:
    return Path(args.state or _state_root())


Clock = Callable[[], float]


def _fetch_vault(args: argparse.Namespace, clock: Clock) -> dict[str, object]:
    state = _state(args)
    clone = vault_clone.locate(state, args.vault)
    fetched = vault_clone.fetch(clone, clock=clock, timeout=args.timeout)
    return {**fetched, "shared": vault_hooks.due_share(clone, state, clock)}


def _queue_comment(args: argparse.Namespace, context: Any) -> dict[str, object]:
    clock = context.clock
    vault_queue.checked([vault_queue.comment(args.record, args.text)])
    prefix = vault_write.events.ids.validate_record_id(args.record).partition("-")[0]
    state = _state(args)
    clone = vault_clone.locate(state, args.vault)
    now = any(os.environ.get(name) for name in ("CI", "BASICLY_TRACKER_EPHEMERAL"))
    target = vault_write.Target(
        clone, state, vault_write.session_of(os.environ), now, clock, prefix
    )
    source = clone.folder / "native-ledger"
    config = vault_config.load(Path.cwd())
    if config is not None and config.prefix == prefix:
        url, _allow_file = vault_clone.vault_source(config.vault)
        if url == clone.url:
            source = config.path.parent / ".basicly" / "ledger"
    queued: dict[str, object] = {}
    context = replace(context, target=target, source=source, queued=queued)
    ledger, context = vault_write.admission(source, context, os.environ)
    commands = _load("commands.py", "basicly_tracker_kit_commands")
    written = commands.comment(ledger, args.record, args.text, context=context)
    if not written:
        queued.update(vault_queue.write(clone, [], state=state, origin=target.origin()))
        queued.update(merged=True, shared=vault_hooks.due_share(clone, state, clock, now=now))
    return queued


def _clone(args: argparse.Namespace) -> Any:
    return vault_clone.locate(_state(args), args.vault)


def _asked(args: argparse.Namespace) -> str:
    if args.vault:
        return str(args.vault)
    if not sys.stdin.isatty():
        return ""
    print(
        "Git address of an empty repository for the vault "
        f"(suggested name: {vault_init.SUGGESTED_NAME}): ",
        end="",
        file=sys.stderr,
    )
    return input().strip()


def _repository_root(start: Path) -> Path | None:
    return next((p for p in (start, *start.parents) if (p / ".git").exists()), None)


def _attach_source(args: argparse.Namespace, url: str) -> Path | None:
    if not args.prefix:
        return None
    root = _repository_root(Path.cwd())
    if args.prefix:
        vault_config.text(url, args.prefix)
        if root is None:
            raise ValueError(
                "vault-init --prefix needs a Git checkout; run it from the base project"
            )
        layout = _load("git_layout.py", "basicly_tracker_kit_git_layout")
        metadata = layout.git_dir(root)
        if metadata is None or not (metadata / "HEAD").is_file():
            raise ValueError("vault-init --prefix needs a valid Git checkout")
        if (metadata / "commondir").is_file():
            raise ValueError("vault-init --prefix must run from the base checkout, not a worktree")
        try:
            actual = vault_clone.git_runner.run(["rev-parse", "--show-toplevel"], root).strip()
        except vault_clone.git_runner.GitRunnerError:
            raise ValueError("vault-init --prefix needs a valid Git checkout") from None
        if Path(actual).resolve() != root.resolve():
            raise ValueError("vault-init --prefix must run in its own base Git checkout")
    ledger = root / ledger_freeze.LEDGER if root is not None and args.prefix else None
    if ledger is not None:
        ledger_freeze.source_path(ledger)
        if vault_config.load(root) is not None:
            raise ValueError(
                "the project already names a vault; use status instead of vault-init --prefix"
            )
        if ledger.with_name(ledger_freeze.ARCHIVE).exists():
            raise ValueError(
                "a ledger archive already exists; finish its interrupted migration first"
            )
    if ledger is not None and ledger_freeze.fingerprint(ledger):
        raise ValueError(
            "the local ledger holds history or a template; initialize the vault without "
            "--prefix, then use migrate --to-vault and migrate --to-vault --freeze"
        )
    return ledger


def _init_vault(args: argparse.Namespace, _clock: Clock) -> dict[str, object]:
    url = _asked(args)
    if not url:
        return {
            "exit": vault_init.FIX,
            "fix": "name the empty repository: vault-init --vault GIT-ADDRESS",
            "suggested_name": vault_init.SUGGESTED_NAME,
        }
    ledger = _attach_source(args, url)
    shown = vault_init.init(url, confirmed=args.yes)
    if shown.get("pushed") and ledger is not None:
        try:
            ledger_freeze.freeze(ledger, url, args.prefix, {})
        except ledger_freeze.FreezeError as exc:
            return {
                **shown,
                "exit": 2,
                "refused": str(exc),
                "fix": "the vault genesis was pushed; preserve the ledger and finish its migration",
            }
        shown["config"] = str(vault_config.CONFIG_PATH)
    return shown


def _orch_note(**fields: object) -> None:
    _orch_kit("note", **fields)


def _orch_pace(record: str, moment: str) -> None:
    _orch_kit("pace", record=record, moment=moment)


def _orch_kit(name: str, **fields: object) -> None:
    source = _HERE.parent / "orch" / "orch_state" / "note.py"
    if not source.is_file():
        return
    spec = importlib.util.spec_from_file_location("basicly_orch_note", source)
    if spec is None or spec.loader is None:
        return
    module = sys.modules.get("basicly_orch_note") or importlib.util.module_from_spec(spec)
    try:
        if "basicly_orch_note" not in sys.modules:
            spec.loader.exec_module(module)
            sys.modules["basicly_orch_note"] = module
        getattr(module, name)(Path.cwd(), os.environ, **fields)
    except OSError, ValueError, ImportError:
        return


def _claim_vault(args: argparse.Namespace, clock: Clock) -> dict[str, object]:
    ask = vault_claim.Ask(
        _clone(args),
        _state(args),
        args.record,
        vault_write.session_of(os.environ, args.session),
        clock,
        name=vault_write.holders.chosen_holder(Path.cwd(), os.environ),
    )
    shown = vault_claim.claim(ask, deadline=args.deadline)
    if shown.get("exit") == vault_claim.LANDED:
        _orch_note(item=args.record, last=f"claimed {args.record}")
        _orch_pace(args.record, "start")
    if shown.get("exit") == vault_claim.UNREACHABLE and vault_init.no_genesis(args.vault):
        return {
            "exit": vault_init.NO_GENESIS,
            "record": args.record,
            "unsettled": "the vault has no genesis commit",
            "next": f"vault-init --vault {args.vault}",
        }
    return shown


def _unassign_vault(args: argparse.Namespace, clock: Clock) -> dict[str, object]:
    session = vault_write.session_of(os.environ, args.session)
    now = any(os.environ.get(name) for name in vault_write.IMMEDIATE)
    target = vault_write.Target(_clone(args), _state(args), session, now, clock)
    return vault_write.release(target, args.record, take=args.take)


def configured(start: Path, asked: str) -> Any:
    config = vault_config.load(Path(start).resolve())
    if config is None and asked:
        raise vault_config.ConfigError(
            f"{asked} reads the vault that {vault_config.CONFIG_PATH} names, and none names "
            f"one here; run it without {asked}"
        )
    return config


def harness_config(root: Path) -> Any:
    config = vault_config.load(Path(root).resolve())
    base = config.path.parent if config is not None else Path(root)
    archive = ledger_freeze.check_source(base / ledger_freeze.LEDGER)
    if config is not None and archive is None:
        raise vault_config.ConfigError(
            f"the configured vault lacks its frozen {ledger_freeze.LEDGER.as_posix()} file "
            "and preserved archive; "
            f"finish `migrate {ledger_freeze.LEDGER.as_posix()} --to-vault --freeze "
            "--prefix NAME --vault ADDRESS` "
            "before using harness hooks"
        )
    return config


def harness_ledger(root: Path, clock: Clock) -> Path | None:
    config = harness_config(root)
    if config is None:
        return None
    return presented(
        config.path.parent / ledger_freeze.LEDGER, clock, all_projects=False, asked=""
    )[0]


def harness_queue_text(root: Path) -> str:
    config = harness_config(root)
    if config is None:
        raise vault_config.ConfigError("no vault is configured here")
    folder = vault_clone.locate(_state_root(), config.vault).folder
    if not folder.is_dir():
        raise OSError(f"the vault clone folder {folder.name} is missing")
    queue = folder / vault_queue.QUEUE_NAME
    return queue.read_text(encoding="utf-8") if queue.exists() else ""


def presented(ledger: Path, clock: Clock, *, all_projects: bool, asked: str) -> Any:
    config = configured(ledger, asked)
    if config is None:
        return None
    ledger_freeze.check(config.path.parent / ledger_freeze.LEDGER)
    clone = vault_clone.locate(_state_root(), config.vault)
    template = Path(ledger) if Path(ledger).is_dir() else None
    want = vault_view.Want(config.prefix, all_projects, template)
    return vault_write.vault_pending.present(clone, want, clock=clock), clone


def view_of(args: argparse.Namespace, clock: Clock) -> Path:
    every = bool(getattr(args, "all_projects", False))
    asked = "--all-projects" if every else ""
    reached = presented(args.directory, clock, all_projects=every, asked=asked)
    return args.directory if reached is None else reached[0]


def read_ledger(directory: Path, clock: Clock) -> Path:
    reached = presented(directory, clock, all_projects=False, asked="")
    return directory if reached is None else reached[0]


def shown(ledger: Path, records: list, clock: Clock) -> list:
    folder, clone = presented(ledger, clock, all_projects=False, asked="--json")
    return vault_write.vault_pending.annotate(folder, vault_view.show(folder, clone, records))


HANDLERS: dict[str, Callable[[argparse.Namespace, Any], dict[str, object]]] = {
    "init-vault": _init_vault,
    "protect-vault": lambda a, _c: vault_push_hooks.install(Path(a.repository)),
    "vault-check": lambda a, _c: vault_shapes.report(a.vault, a.ref),
    "vault-show": lambda a, _c: _vault_show(a),
    "fetch": _fetch_vault,
    "comment-vault": _queue_comment,
    "hook-vault": lambda a, c: vault_hooks.hook(a.event, _clone(a), _state(a), clock=c),
    "status-vault": lambda a, c: vault_hooks.status(_clone(a), clock=c),
    "fsck-vault": lambda a, c: vault_repair.check(_clone(a), _state(a), vars(a), c),
    "reclone-vault": lambda a, c: vault_repair.reclone(_clone(a), clock=c),
    "claim-vault": _claim_vault,
    "unassign-vault": _unassign_vault,
    "sync-vault": lambda a, c: vault_share.share(
        _clone(a), _state(a), plan=vault_share.Plan(c, urgent=a.urgent, deadline_s=a.deadline)
    ),
    "commit-msg-vault": lambda a, c: vault_commit_hook.check(
        vault_commit_hook.Commit(
            _clone(a),
            _state(a),
            Path(a.message),
            vault_write.session_of(os.environ, a.session),
            c,
        )
    ),
}
