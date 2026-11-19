from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
MINIMUM_PYTHON = (3, 14)


def require_runtime() -> None:
    if sys.version_info < MINIMUM_PYTHON:
        raise SystemExit(
            "basicly-tracker requires Python 3.14 or later. Run "
            "`uvx --python '>=3.14' basicly-tracker` to provision a suitable runtime."
        )


def _load(name: str) -> Any:
    key = f"basicly_tracker_kit_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ValueError("Tracker bootstrap is incomplete; reinstall basicly-tracker with uv.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def run(directory: Path, clock: Callable[[], float]) -> tuple[int, dict[str, object]]:
    require_runtime()
    git = _load("git_runner")
    root = Path(git.run(["rev-parse", "--show-toplevel"], directory).strip()).resolve()
    config = _load("vault_config").load(root)
    ledger = root / ".basicly/ledger"
    backend = "ledger"
    head = ""
    if config is not None:
        adapter = _load("vault_cli")
        adapter.harness_config(root)
        clones = _load("vault_clone")
        state = adapter._state_root()
        clone = clones.locate(state, config.vault)
        fetched = clones.fetch(clone, clock=clock)
        if not fetched.get("fetched") or fetched.get("retracted"):
            raise ValueError(
                "Tracker memory could not be refreshed. Restore vault access and credentials, "
                "then run `basicly-tracker bootstrap` again before starting implementation."
            )
        if clones.ended(clone):
            raise ValueError(
                "This tracker vault is retired. Update the repository tracker binding before "
                "starting implementation."
            )
        view = _load("vault_view")
        ledger = view.present(clone, view.Want(config.prefix), clock=clock)
        backend = "vault"
        head = str(fetched["head"])
    elif not ledger.is_dir():
        raise ValueError(
            "This repository has no persistent tracker memory. Run repository onboarding "
            "with `basicly-tracker init --scope project` before starting implementation."
        )
    events = _load("events")
    found, errors = events.read_events(ledger)
    if errors:
        raise ValueError(
            f"Tracker memory contains unreadable events. Run `basicly-tracker fsck {ledger}` "
            "and repair the named input before starting implementation."
        )
    records = events.fold(found).records
    return 0, {
        "schema": "basicly.tracker.bootstrap.v1",
        "ready": True,
        "repository": str(root),
        "backend": backend,
        "prefix": config.prefix if config is not None else "",
        "head": head,
        "records": len(records),
        "memory": str(ledger),
    }


def prepare(directory: Path, *, clock: Callable[[], float] | None = None) -> dict[str, object]:
    require_runtime()
    git = _load("git_runner")
    events = _load("events")
    try:
        code, report = _load("cli").invoke(
            argparse.Namespace(command="bootstrap", repository=directory, clock=clock)
        )
    except git.GitRunnerError, events.LedgerError:
        raise ValueError(
            "Persistent tracker memory is unavailable. Check Git, vault access and "
            "credentials, then run `basicly-tracker bootstrap` before implementation."
        ) from None
    if code != 0:
        raise ValueError(str(report.get("refused") or "Tracker bootstrap refused startup."))
    return report


def main(argv: list[str] | None = None) -> int:
    require_runtime()
    parser = argparse.ArgumentParser(description="Establish persistent tracker memory before work.")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        report = prepare(args.repository)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"tracker bootstrap: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
