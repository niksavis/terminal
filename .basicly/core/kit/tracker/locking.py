from __future__ import annotations

import errno
import os
from pathlib import Path

CONTENTION = frozenset({errno.EACCES, errno.EAGAIN})


def try_exclusive(handle: int) -> bool:
    try:
        if os.name == "nt":
            import msvcrt  # noqa: PLC0415 - the Windows backend is unavailable on POSIX

            os.lseek(handle, 0, os.SEEK_SET)
            msvcrt.locking(handle, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # noqa: PLC0415 - the POSIX backend is unavailable on Windows

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in CONTENTION:
            return False
        raise
    return True


def is_held(path: Path) -> bool:
    try:
        handle = os.open(str(path), os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        return not try_exclusive(handle)
    finally:
        os.close(handle)
