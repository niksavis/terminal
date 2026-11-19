from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass


@dataclass(frozen=True)
class Done:
    code: int
    out: str
    err: str


def environ() -> dict[str, str]:
    return dict(os.environ)


def which(name: str, path: str | None) -> str | None:
    return shutil.which(name, path=path)


def capture(argv: list[str], timeout: float) -> Done:
    done = subprocess.run(  # nosec B603 - list argv from the caller, no shell
        argv, capture_output=True, text=True, check=False, timeout=timeout
    )
    return Done(done.returncode, done.stdout, done.stderr)


def quiet(argv: list[str], env: dict[str, str], timeout: float) -> None:
    subprocess.run(  # nosec B603 - list argv from the caller, no shell
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
        env=env,
    )
