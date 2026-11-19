from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

from mail_root import ENV, FOLDER, cmd_init, find_root
from mail_store import (
    NAME,
    PROG,
    Mail,
    RefusedError,
    deliver,
    header,
    need_name,
    now_iso,
    place,
    subject_of,
)

POLL_SECONDS = 2.0
USAGE = f"""{PROG}: messages and locks between agents on one machine, one file per message.

  init [folder]                      create {FOLDER} in folder (default: here) and git-ignore it
  root                               print the mailbox folder that this command uses
  join <prefix>                      take the first free name <prefix>-N and print it
  join --as <name>                   take exactly this name; refused when it is taken
  rejoin <name>                      continue under a name you already hold
  send <from> <to|all> <subject>     body on standard input
  wait <name> [seconds]              block until a message arrives (default 600)
  read <name>                        print every new message and mark it read
  peek <name>                        list new messages, mark nothing
  status <name> <text>               publish one line: what you do now
  who                                every agent: unread count, last seen, status
  log [count]                        the newest messages of all agents (default 20)
  lock <resource> <name> <note>      take a lock; refused when it is held
  unlock <resource> <name> [--break] release a lock; --break releases another agent's lock
  locks                              every lock and its holder

The folder is found in this order: {ENV}, then {FOLDER} with its marker in this folder
or a parent, then the same search from the main worktree of this git repository.

Exit codes: 0 done, 1 refused or wrong use, 2 wait ended with no message, 3 lock is held.
"""


def cmd_root(mail: Mail, how: str, args: list[str]) -> int:
    if args:
        raise RefusedError(f"usage: {PROG} root")
    print(f"{mail.root} ({how})")
    return 0


def cmd_join(mail: Mail, args: list[str]) -> int:
    mail.need_boxes()
    if not args:
        raise RefusedError(f"usage: {PROG} join <prefix>   or   {PROG} join --as <name>")
    if args[0] == "--as":
        if len(args) != 2:
            raise RefusedError(f"usage: {PROG} join --as <name>")
        name = need_name(args[1])
        try:
            (mail.boxes / name).mkdir()
        except FileExistsError:
            raise RefusedError(
                f"the name {name!r} is taken. If it is yours, run: {PROG} rejoin {name}"
            ) from None
    else:
        prefix = need_name(args[0], "prefix")
        for number in range(1, 100):
            name = f"{prefix}-{number}"
            try:
                (mail.boxes / name).mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RefusedError(f"no free name for the prefix {prefix!r}")
    mail.make_box(name)
    print(name)
    print(f"mail root: {mail.root}", file=sys.stderr)
    return 0


def cmd_rejoin(mail: Mail, args: list[str]) -> int:
    if len(args) != 1:
        raise RefusedError(f"usage: {PROG} rejoin <name>")
    name = mail.need_member(args[0])
    mail.touch_seen(name)
    print(name)
    return 0


def read_body() -> str:
    stream = sys.stdin
    if stream is None or stream.isatty():
        raise RefusedError("no body: pipe the message text into the command")
    try:
        body = stream.buffer.read().decode("utf-8").replace("\r\n", "\n").rstrip("\n")
    except UnicodeDecodeError:
        raise RefusedError("the body is not UTF-8 text: send it as UTF-8") from None
    if not body.strip():
        raise RefusedError("empty body: pipe the message text into the command")
    return body


def cmd_send(mail: Mail, args: list[str]) -> int:
    if len(args) != 3 or not all(args):
        raise RefusedError(
            f"usage: {PROG} send <from> <to|all> <subject>   with the body on standard input"
        )
    sender, receiver, subject = args
    mail.need_member(sender)
    if "\n" in subject or "\r" in subject:
        raise RefusedError("the subject must be one line")
    if receiver == "all":
        targets = [member for member in mail.members() if member != sender]
        if not targets:
            raise RefusedError("no other agent has joined")
    else:
        targets = [mail.need_member(receiver)]
    body = read_body()
    text = f"From: {sender}\nTo: {receiver}\nDate: {now_iso()}\nSubject: {subject}\n\n{body}\n"
    for target in targets:
        name = deliver(mail.boxes / target, sender, text)
        print(f"sent to {target}: {name}")
    mail.touch_seen(sender)
    return 0


def show_new(mail: Mail, name: str) -> int:
    found = mail.list_new(name)
    for entry in found:
        print(f"{entry}  {subject_of(mail.boxes / name / 'new' / entry)}")
    if not found:
        print("no new message")
    return len(found)


def cmd_peek(mail: Mail, args: list[str]) -> int:
    if len(args) != 1:
        raise RefusedError(f"usage: {PROG} peek <name>")
    name = mail.need_member(args[0])
    mail.touch_seen(name)
    show_new(mail, name)
    return 0


def cmd_read(mail: Mail, args: list[str]) -> int:
    if len(args) != 1:
        raise RefusedError(f"usage: {PROG} read <name>")
    name = mail.need_member(args[0])
    mail.touch_seen(name)
    found = mail.list_new(name)
    for entry in found:
        source = mail.boxes / name / "new" / entry
        print(f"=== {entry}")
        print(source.read_text(encoding="utf-8", errors="replace"))
        try:
            place(source, mail.boxes / name / "cur" / entry)
        except FileExistsError:
            print(f"{entry} stays in new: cur holds a message of that name", file=sys.stderr)
    if not found:
        print("no new message")
    return 0


def cmd_wait(mail: Mail, args: list[str]) -> int:
    if not 1 <= len(args) <= 2:
        raise RefusedError(f"usage: {PROG} wait <name> [seconds]")
    name = mail.need_member(args[0])
    limit_text = args[1] if len(args) == 2 else "600"
    if not limit_text.isdigit():
        raise RefusedError("the wait time must be a whole number of seconds")
    end = time.monotonic() + int(limit_text)
    while True:
        mail.touch_seen(name)
        if mail.list_new(name):
            show_new(mail, name)
            print(f"read them with: {PROG} read {name}")
            return 0
        left = end - time.monotonic()
        if left <= 0:
            print(f"no new message after {limit_text} seconds. Run the wait again.")
            return 2
        time.sleep(min(POLL_SECONDS, left))


def cmd_status(mail: Mail, args: list[str]) -> int:
    if len(args) < 2:
        raise RefusedError(f"usage: {PROG} status <name> <text>")
    name = mail.need_member(args[0])
    text = " ".join(args[1:])
    if "\n" in text or "\r" in text:
        raise RefusedError("the status must be one line")
    part = mail.boxes / name / f"status.{os.getpid()}.{secrets.token_hex(4)}.tmp"
    part.write_text(f"{now_iso()} {text}\n", encoding="utf-8")
    part.replace(mail.boxes / name / "status")
    mail.touch_seen(name)
    print(f"status of {name} published")
    return 0


def first_line(path: Path, default: str) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return default
    return lines[0] if lines else default


def cmd_who(mail: Mail, args: list[str]) -> int:
    if args:
        raise RefusedError(f"usage: {PROG} who")
    for member in mail.members():
        count = len(mail.list_new(member))
        seen = first_line(mail.boxes / member / "seen", "never")
        status = first_line(mail.boxes / member / "status", "no status")
        print(f"{member:<18} unread {count:<3} seen {seen} | {status}")
    return 0


def cmd_log(mail: Mail, args: list[str]) -> int:
    if len(args) > 1 or (args and not args[0].isdigit()):
        raise RefusedError(f"usage: {PROG} log [count]")
    count = int(args[0]) if args else 20
    entries: list[tuple[str, Path, str, str]] = []
    for member in mail.members():
        for state in ("new", "cur"):
            label = "NEW " if state == "new" else "read"
            entries.extend(
                (path.name, path, member, label)
                for path in (mail.boxes / member / state).glob("*.md")
            )
    entries.sort()
    for name, path, member, state in entries[-count:] if count else []:
        print(f"{name[:15]}Z  {header(path, 'From')} -> {member:<16} {state}  {subject_of(path)}")
    return 0


def cmd_lock(mail: Mail, args: list[str]) -> int:
    if len(args) < 3:
        raise RefusedError(f"usage: {PROG} lock <resource> <name> <note>")
    resource = need_name(args[0], "resource")
    name = mail.need_member(args[1])
    note = " ".join(args[2:])
    if "\n" in note or "\r" in note:
        raise RefusedError("the note must be one line")
    if not mail.locks.is_dir():
        raise RefusedError(f"{mail.locks} is missing. Run: {PROG} init {mail.root.parent}")
    stage = mail.locks / f".stage-{os.getpid()}-{secrets.token_hex(6)}"
    stage.mkdir()
    (stage / "owner").write_text(f"{name} {now_iso()} {note}\n", encoding="utf-8")
    try:
        stage.rename(mail.locks / resource)
    except OSError:
        (stage / "owner").unlink(missing_ok=True)
        stage.rmdir()
        if (mail.locks / resource).exists():
            holder = first_line(mail.locks / resource / "owner", "holder not written")
            raise RefusedError(
                f"lock {resource!r} is held: {holder}. Do not go on. Try again later.", 3
            ) from None
        raise
    print(f"lock {resource!r} taken by {name}")
    return 0


def cmd_unlock(mail: Mail, args: list[str]) -> int:
    force = "--break" in args
    rest = [arg for arg in args if arg != "--break"]
    if len(rest) != 2:
        raise RefusedError(f"usage: {PROG} unlock <resource> <name> [--break]")
    resource = need_name(rest[0], "resource")
    name = mail.need_member(rest[1])
    held = mail.locks / resource
    if not held.is_dir():
        raise RefusedError(f"lock {resource!r} is not held")
    holder = first_line(held / "owner", "").split(" ", 1)[0]
    if holder != name:
        if not force:
            raise RefusedError(
                f"lock {resource!r} is held by {holder!r}, not by {name!r}. Only the holder "
                f"releases it; --break releases it anyway"
            )
        print(f"breaking lock {resource!r} of {holder!r}")
    gone = mail.locks / f".gone-{os.getpid()}-{secrets.token_hex(6)}"
    try:
        held.rename(gone)
    except FileNotFoundError:
        raise RefusedError(f"lock {resource!r} was released by another command") from None
    for entry in gone.iterdir():
        entry.unlink()
    gone.rmdir()
    print(f"lock {resource!r} released")
    return 0


def cmd_locks(mail: Mail, args: list[str]) -> int:
    if args:
        raise RefusedError(f"usage: {PROG} locks")
    held = (
        sorted(
            entry for entry in mail.locks.iterdir() if NAME.fullmatch(entry.name) and entry.is_dir()
        )
        if mail.locks.is_dir()
        else []
    )
    for entry in held:
        print(f"{entry.name:<16} {first_line(entry / 'owner', 'holder not written')}")
    if not held:
        print("no lock is held")
    return 0


COMMANDS = {
    "join": cmd_join,
    "rejoin": cmd_rejoin,
    "send": cmd_send,
    "wait": cmd_wait,
    "read": cmd_read,
    "peek": cmd_peek,
    "status": cmd_status,
    "who": cmd_who,
    "log": cmd_log,
    "lock": cmd_lock,
    "unlock": cmd_unlock,
    "locks": cmd_locks,
}


def run(argv: list[str], cwd: Path) -> int:
    command = argv[0] if argv else "help"
    args = argv[1:]
    if command in ("help", "-h", "--help"):
        print(USAGE, end="")
        return 0
    if command == "init":
        return cmd_init(cwd, args)
    if command != "root" and command not in COMMANDS:
        raise RefusedError(f"unknown command {command!r}. Run: {PROG} help")
    root, how = find_root(cwd)
    mail = Mail(root)
    if command == "root":
        return cmd_root(mail, how, args)
    return COMMANDS[command](mail, args)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    try:
        return run(list(sys.argv[1:] if argv is None else argv), Path.cwd())
    except RefusedError as refusal:
        print(f"{PROG}: {refusal}", file=sys.stderr)
        return refusal.code


if __name__ == "__main__":
    sys.exit(main())
