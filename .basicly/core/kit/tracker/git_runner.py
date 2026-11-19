from __future__ import annotations

import contextlib
import os
import re
import secrets
import signal
import subprocess  # nosec B404
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 30.0
STOP_WAIT = 5.0
END_OF_OPTIONS = "--end-of-options"

_COMMIT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_WRITER_ID = re.compile(r"[0-9a-f]{32}")
_HOST = r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
_USER = r"[a-z_][a-z0-9_.-]{0,31}"
_PATH = r"[A-Za-z0-9._~/%+-]+"
_HTTPS_URL = re.compile(rf"https://{_HOST}(?::[0-9]{{1,5}})?/{_PATH}")
_SSH_URL = re.compile(rf"ssh://(?:{_USER}@)?{_HOST}(?::[0-9]{{1,5}})?/{_PATH}")
_SCP_URL = re.compile(rf"{_USER}@{_HOST}:(?!-){_PATH}")
_FILE_URL = re.compile(r"file:///[^\x00-\x1f\x7f]+")
_UNSAFE = re.compile(r"[\x00-\x20\x7f]")

_REPOSITORY_VARIABLES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


class GitRunnerError(Exception):
    pass


class GitValueError(GitRunnerError):
    pass


class GitMissingError(GitRunnerError):
    pass


class GitTimeoutError(GitRunnerError):
    pass


class GitCommandError(GitRunnerError):
    def __init__(self, verb: str, returncode: int, stderr: str) -> None:
        super().__init__(f"git {verb} failed with exit code {returncode}")
        self.verb = verb
        self.returncode = returncode
        self.stderr = stderr


def environment_value(name: str) -> str:
    return os.environ.get(name, "")


def _refuse(kind: str, value: object, rule: str) -> GitValueError:
    shown = value[:80] if isinstance(value, str) else type(value).__name__
    return GitValueError(f"refused {kind} {shown!r}: {rule}")


def commit_id(value: str) -> str:
    if not isinstance(value, str) or not _COMMIT_ID.fullmatch(value):
        raise _refuse("commit id", value, "it must be 40 or 64 lowercase hex characters")
    return value


def writer_id(value: str) -> str:
    if not isinstance(value, str) or not _WRITER_ID.fullmatch(value):
        raise _refuse("writer id", value, "it must be 32 lowercase hex characters")
    return value


def new_writer_id() -> str:
    return secrets.token_hex(16)


def remote_url(value: str, *, allow_file: bool = False) -> str:
    if isinstance(value, str) and not value.startswith("-") and not _UNSAFE.search(value):
        if any(form.fullmatch(value) for form in (_HTTPS_URL, _SSH_URL, _SCP_URL)):
            return value
        if allow_file and _FILE_URL.fullmatch(value):
            return value
    raise GitValueError(
        "refused a backlog URL: use an https://, ssh:// or user@host:path address "
        "with no password or token in it"
    )


def _protocols(allow_file: bool) -> list[str]:
    return ["https", "ssh", *(["file"] if allow_file else [])]


def _protocol_config(allow_file: bool) -> list[str]:
    allowed = _protocols(allow_file)
    config = ["-c", "protocol.allow=never"]
    for name in allowed:
        config += ["-c", f"protocol.{name}.allow=always"]
    return config


def _child_env(extra: Mapping[str, str] | None, allow_file: bool) -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name not in _REPOSITORY_VARIABLES}
    env.update(extra or {})
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ALLOW_PROTOCOL"] = ":".join(_protocols(allow_file))
    return env


def _group_options() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _stop(process: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        process.kill()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    try:
        process.communicate(timeout=STOP_WAIT)
    except subprocess.TimeoutExpired:
        process.kill()


def run(
    args: Sequence[str],
    cwd: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    allow_file: bool = False,
    env: Mapping[str, str] | None = None,
) -> str:
    if not args or not all(isinstance(arg, str) for arg in args):
        raise GitValueError("refused git arguments: pass a non-empty list of strings")
    verb = args[0]
    argv = ["git", *_protocol_config(allow_file), *args]
    try:
        process = subprocess.Popen(  # nosec B603
            argv,
            cwd=str(cwd),
            env=_child_env(env, allow_file),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            **_group_options(),
        )
    except OSError as exc:
        raise GitMissingError("git could not be started: install git and put it on PATH") from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(process)
        raise GitTimeoutError(
            f"git {verb} did not finish within {timeout:g} s and was stopped"
        ) from None
    if process.returncode != 0:
        raise GitCommandError(verb, process.returncode, stderr)
    return stdout
