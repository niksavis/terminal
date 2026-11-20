from __future__ import annotations

from typing import Any

DIRECTORY_HELP = "the ledger directory"


def add_parsers(sub: Any) -> None:
    add_sync_parser(sub)
    add_vault_parsers(sub)


def add_vault_parsers(sub: Any) -> None:
    shapes = sub.add_parser("vault-check", help="sort each vault commit into valid or quarantined")
    shapes.add_argument("vault", help="the vault repository, bare or not")
    shapes.add_argument("--ref", default="HEAD", help="the branch or commit to read")
    shown = sub.add_parser("vault-show", help="fold a vault and show one record's holder")
    shown.add_argument("vault", help="the vault repository, bare or not")
    shown.add_argument("record", help="the record id")
    shown.add_argument("--ref", default="HEAD", help="the branch or commit to read")
    fetched = sub.add_parser("fetch", help="clone a vault bare once, then fetch it under a lock")
    fetched.add_argument("--vault", required=True, help="the vault URL or local repository")
    fetched.add_argument("--state", help="the machine state folder (default: per user)")
    fetched.add_argument("--timeout", type=float, default=30.0, help="seconds per git call")
    status = sub.add_parser("status", help="list the queued local events a vault has not received")
    status.add_argument("--vault", required=True, help="the vault URL or local repository")
    status.add_argument("--state", help="the machine state folder (default: per user)")


def add_sync_parser(sub: Any) -> None:
    mirrored = sub.add_parser("sync", help="re-import the tracker this ledger mirrors")
    mirrored.add_argument("directory", help=DIRECTORY_HELP)
    mirrored.add_argument("--root", default=".", help="the repository that holds the source")
    mirrored.add_argument("--dry-run", action="store_true", help="report and write nothing")
