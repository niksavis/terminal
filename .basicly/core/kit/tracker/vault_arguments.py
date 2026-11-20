from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NoReturn


class _Form(argparse.ArgumentParser):
    example = ""

    def error(self, message: str) -> NoReturn:
        hint = f"; the form is: {self.example}" if self.example else ""
        self.exit(2, f"{self.format_usage()}{self.prog}: error: {message}{hint}\n")


def _form(verb: str, text: str, command: str) -> _Form:
    parser = _Form(prog=f"cli.py {verb}", description=text)
    parser.add_argument("verb", choices=[verb], help=argparse.SUPPRESS)
    parser.add_argument("--vault", required=True, help="the vault URL or local repository")
    parser.add_argument("--state", help="the machine state folder (default: per user)")
    parser.set_defaults(command=command)
    return parser


def comment() -> argparse.ArgumentParser:
    parser = _form("comment", "queue a vault comment", "comment-vault")
    parser.example = "cli.py comment RECORD --vault URL --text TEXT"
    parser.add_argument("record", help="the record id")
    parser.add_argument("--text", required=True, help="the comment, redacted before it is queued")
    return parser


def sync() -> argparse.ArgumentParser:
    parser = _form("sync", "share a vault's queue", "sync-vault")
    parser.add_argument("--urgent", action="store_true", help="retry until --deadline passes")
    parser.add_argument("--deadline", type=float, default=10.0, help="seconds for an urgent share")
    return parser


def fsck() -> argparse.ArgumentParser:
    parser = _form("fsck", "report or repair a vault clone", "fsck-vault")
    parser.add_argument("--repair", action="store_true", help="re-queue lines a rewrite dropped")
    parser.add_argument("--accept-rewrite", metavar="HEAD", help="accept the fetched head")
    parser.add_argument("--purge", action="store_true", help="confirm dropping retracted refs")
    return parser


def reclone() -> argparse.ArgumentParser:
    return _form("reclone", "clone a vault again, keeping its refs", "reclone-vault")


def hook() -> argparse.ArgumentParser:
    parser = _form("hook", "fetch or share from an agent hook", "hook-vault")
    parser.add_argument("event", choices=["session-start", "prompt", "stop", "session-end"])
    return parser


def claim() -> argparse.ArgumentParser:
    parser = _form("claim", "claim a record in the vault within 30 s", "claim-vault")
    parser.add_argument("record", help="the record id")
    parser.add_argument("--session", help="the session (default: BASICLY_TRACKER_SESSION)")
    parser.add_argument("--deadline", type=float, default=30.0, help="seconds for the whole claim")
    return parser


def unassign() -> argparse.ArgumentParser:
    parser = _form("unassign", "give a vault record back", "unassign-vault")
    parser.add_argument("record", help="the record id")
    parser.add_argument("--session", help="the session (default: BASICLY_TRACKER_SESSION)")
    parser.add_argument("--take", action="store_true", help="release another session's claim")
    return parser


def commit_msg() -> argparse.ArgumentParser:
    parser = _form("commit-msg", "check a commit message against vault claims", "commit-msg-vault")
    parser.add_argument("message", help="the commit message file git passes to commit-msg")
    parser.add_argument("--session", help="the session (default: BASICLY_TRACKER_SESSION)")
    return parser


def status() -> argparse.ArgumentParser:
    return _form("status", "show the data age without a network call", "status-vault")


def protect() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py vault-protect",
        description="Install the vault push guard in an existing clone.",
    )
    parser.add_argument("verb", choices=["vault-protect"], help=argparse.SUPPRESS)
    parser.add_argument("--repository", type=Path, required=True, help="the existing vault clone")
    parser.set_defaults(command="protect-vault")
    return parser


def init() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py vault-init", description="push the genesis into an empty vault repository"
    )
    parser.add_argument("verb", choices=["vault-init"], help=argparse.SUPPRESS)
    parser.add_argument("--vault", help="the git address of an empty repository; asked if absent")
    parser.add_argument("--prefix", help="the project prefix to write into .basicly-tracker.toml")
    parser.add_argument(
        "--yes", action="store_true", help="push after printing what will be pushed"
    )
    parser.set_defaults(command="init-vault", state=None)
    return parser


FORMS: dict[str, Callable[[], argparse.ArgumentParser]] = {
    "comment": comment,
    "sync": sync,
    "fsck": fsck,
    "reclone": reclone,
    "hook": hook,
    "status": status,
    "claim": claim,
    "unassign": unassign,
    "commit-msg": commit_msg,
    "vault-init": init,
    "vault-protect": protect,
}
VAULT_ONLY = frozenset({"vault-init", "vault-protect"})
LEDGER_FORMS = frozenset({"comment", "claim", "unassign", "sync", "fsck"})


def names_a_ledger(argv: Sequence[str]) -> bool:
    if len(argv) < 2 or argv[0] not in LEDGER_FORMS or argv[1].startswith("-"):
        return False
    given = argv[1]
    return "/" in given or "\\" in given or Path(given).is_dir()


def routed_verbs(argv: Sequence[str]) -> frozenset:
    return frozenset(FORMS) - {"vault-protect"} - ({argv[0]} if names_a_ledger(argv) else set())
