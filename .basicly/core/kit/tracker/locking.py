from __future__ import annotations

import ctypes
import errno
import importlib
import os
from ctypes import wintypes
from pathlib import Path

CONTENTION = frozenset({errno.EACCES, errno.EAGAIN})
LEDGER_LOCK_NAME = ".events.lock"


def open_movable(path: Path) -> int:
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        generic_read_write = 0xC0000000
        share_read_write_delete = 0x00000007
        open_always = 4
        normal_file = 0x80
        handle = create(
            str(path),
            generic_read_write,
            share_read_write_delete,
            None,
            open_always,
            normal_file,
            None,
        )
        if handle is None or handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except OSError:
            close = kernel.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close.restype = wintypes.BOOL
            close(handle)
            raise
    return os.open(str(path), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)


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
