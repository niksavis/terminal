from __future__ import annotations

import ctypes
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import wintypes
from functools import lru_cache
from pathlib import Path
from typing import Any

POINTER = ctypes.c_void_p
POINTER_OUT = ctypes.POINTER(POINTER)
DWORD_OUT = ctypes.POINTER(wintypes.DWORD)
DACL_INFORMATION = 4
OWNER_INFORMATION = 1
PROTECTED_DACL_INFORMATION = 0x80000000
FILE_ALL_ACCESS = 0x1F01FF


class DefaultOwnerError(OSError):
    pass


class SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.DWORD),
        ("descriptor", POINTER),
        ("inherit", wintypes.BOOL),
    ]


class FileAttributes(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


class FileStandard(ctypes.Structure):
    _fields_ = [
        ("allocated", ctypes.c_longlong),
        ("size", ctypes.c_longlong),
        ("links", wintypes.DWORD),
        ("pending", ctypes.c_ubyte),
        ("directory", ctypes.c_ubyte),
    ]


class AclSize(ctypes.Structure):
    _fields_ = [
        ("count", wintypes.DWORD),
        ("used", wintypes.DWORD),
        ("free", wintypes.DWORD),
    ]


class AllowedAce(ctypes.Structure):
    _fields_ = [
        ("kind", ctypes.c_ubyte),
        ("flags", ctypes.c_ubyte),
        ("size", wintypes.WORD),
        ("mask", wintypes.DWORD),
        ("sid", wintypes.DWORD),
    ]


@lru_cache(maxsize=1)
def _api() -> tuple[Any, Any]:
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        raise OSError("Private Windows state requires native Windows security APIs.")
    kernel, security = (
        loader("kernel32", use_last_error=True),
        loader("advapi32", use_last_error=True),
    )
    kernel_signatures = {
        "GetCurrentProcess": (wintypes.HANDLE, []),
        "CloseHandle": (wintypes.BOOL, [wintypes.HANDLE]),
        "LocalFree": (POINTER, [POINTER]),
        "CreateDirectoryW": (wintypes.BOOL, [wintypes.LPCWSTR, POINTER]),
        "CreateFileW": (
            wintypes.HANDLE,
            [
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                POINTER,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            ],
        ),
        "GetFileInformationByHandleEx": (
            wintypes.BOOL,
            [wintypes.HANDLE, ctypes.c_int, POINTER, wintypes.DWORD],
        ),
    }
    security_signatures = {
        "OpenProcessToken": (wintypes.BOOL, [wintypes.HANDLE, wintypes.DWORD, POINTER_OUT]),
        "GetTokenInformation": (
            wintypes.BOOL,
            [wintypes.HANDLE, ctypes.c_int, POINTER, wintypes.DWORD, DWORD_OUT],
        ),
        "ConvertSidToStringSidW": (wintypes.BOOL, [POINTER, ctypes.POINTER(wintypes.LPWSTR)]),
        "ConvertStringSecurityDescriptorToSecurityDescriptorW": (
            wintypes.BOOL,
            [wintypes.LPCWSTR, wintypes.DWORD, POINTER_OUT, DWORD_OUT],
        ),
        "GetSecurityDescriptorDacl": (
            wintypes.BOOL,
            [POINTER, ctypes.POINTER(wintypes.BOOL), POINTER_OUT, ctypes.POINTER(wintypes.BOOL)],
        ),
        "GetSecurityDescriptorControl": (
            wintypes.BOOL,
            [POINTER, ctypes.POINTER(wintypes.WORD), DWORD_OUT],
        ),
        "SetSecurityInfo": (
            wintypes.DWORD,
            [wintypes.HANDLE, ctypes.c_int, wintypes.DWORD, POINTER, POINTER, POINTER, POINTER],
        ),
        "GetSecurityInfo": (
            wintypes.DWORD,
            [
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.DWORD,
                POINTER_OUT,
                POINTER_OUT,
                POINTER_OUT,
                POINTER_OUT,
                POINTER_OUT,
            ],
        ),
        "GetAclInformation": (wintypes.BOOL, [POINTER, POINTER, wintypes.DWORD, ctypes.c_int]),
        "GetAce": (wintypes.BOOL, [POINTER, wintypes.DWORD, POINTER_OUT]),
        "EqualSid": (wintypes.BOOL, [POINTER, POINTER]),
    }
    for library, signatures in ((kernel, kernel_signatures), (security, security_signatures)):
        for name, (result, arguments) in signatures.items():
            function = getattr(library, name)
            function.restype, function.argtypes = result, arguments
    return kernel, security


def _error(code: int | None = None) -> OSError:
    factory, last_error = getattr(ctypes, "WinError", None), getattr(ctypes, "get_last_error", None)
    if factory is None or last_error is None:
        return OSError("Private Windows state requires native Windows security APIs.")
    return factory(code if code is not None else last_error())


def _check(success: Any) -> None:
    if not success:
        raise _error()


def _token_data(security: Any, token: Any, kind: int) -> Any:
    size = wintypes.DWORD()
    security.GetTokenInformation(token, kind, None, 0, ctypes.byref(size))
    if not size.value:
        raise _error()
    buffer = ctypes.create_string_buffer(size.value)
    _check(security.GetTokenInformation(token, kind, buffer, size.value, ctypes.byref(size)))
    return buffer


def _user(kernel: Any, security: Any) -> Any:
    token = POINTER()
    _check(security.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)))
    try:
        user, owner = _token_data(security, token, 1), _token_data(security, token, 4)
        user_sid = ctypes.cast(user, ctypes.POINTER(POINTER))[0]
        owner_sid = ctypes.cast(owner, ctypes.POINTER(POINTER))[0]
        if not user_sid or not owner_sid or not security.EqualSid(user_sid, owner_sid):
            raise DefaultOwnerError("The Windows default owner differs from the current user.")
        return user
    finally:
        kernel.CloseHandle(token)


def _descriptor(kernel: Any, security: Any, sid: int) -> Any:
    name, descriptor = wintypes.LPWSTR(), POINTER()
    _check(security.ConvertSidToStringSidW(sid, ctypes.byref(name)))
    try:
        _check(
            security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                f"O:{name.value}D:P(A;OICI;FA;;;{name.value})", 1, ctypes.byref(descriptor), None
            )
        )
        return descriptor
    finally:
        kernel.LocalFree(name)


def _verify(kernel: Any, security: Any, handle: Any, sid: int, *, directory: bool) -> bool:
    owner, acl, descriptor = POINTER(), POINTER(), POINTER()
    code = security.GetSecurityInfo(
        handle,
        1,
        OWNER_INFORMATION | DACL_INFORMATION,
        ctypes.byref(owner),
        None,
        ctypes.byref(acl),
        None,
        ctypes.byref(descriptor),
    )
    if code:
        raise _error(code)
    try:
        if not owner.value or not security.EqualSid(owner, sid):
            raise OSError("The vault state is owned by another principal.")
        if not acl.value:
            raise OSError("The vault state has no restrictive access list.")
        size, pointer = AclSize(), POINTER()
        _check(security.GetAclInformation(acl, ctypes.byref(size), ctypes.sizeof(size), 2))
        if size.count != 1:
            raise OSError("The vault state grants access to another principal.")
        _check(security.GetAce(acl, 0, ctypes.byref(pointer)))
        if not pointer.value:
            raise OSError("The vault state has no valid access entry.")
        ace = ctypes.cast(pointer, ctypes.POINTER(AllowedAce)).contents
        if (
            ace.kind != 0
            or ace.flags & ~0x10 != (3 if directory else 0)
            or ace.mask != FILE_ALL_ACCESS
            or not security.EqualSid(pointer.value + AllowedAce.sid.offset, sid)
        ):
            raise OSError("The vault state is not private to the current user.")
        control, revision = wintypes.WORD(), wintypes.DWORD()
        _check(
            security.GetSecurityDescriptorControl(
                descriptor, ctypes.byref(control), ctypes.byref(revision)
            )
        )
        return bool(control.value & 0x1000)
    finally:
        kernel.LocalFree(descriptor)


@contextmanager
def _opened(kernel: Any, path: Path, *, root: bool) -> Iterator[tuple[Any, bool]]:
    handle = kernel.CreateFileW(str(path), 0x60080, 3 if root else 7, None, 3, 0x2200000, None)
    if handle == POINTER(-1).value:
        raise _error()
    try:
        actual = FileAttributes()
        _check(
            kernel.GetFileInformationByHandleEx(
                handle, 9, ctypes.byref(actual), ctypes.sizeof(actual)
            )
        )
        directory = bool(actual.attributes & 0x10)
        if actual.attributes & 0x400 or (root and not directory):
            raise OSError("The vault state must be a directory without a reparse point.")
        if not directory:
            standard = FileStandard()
            _check(
                kernel.GetFileInformationByHandleEx(
                    handle, 1, ctypes.byref(standard), ctypes.sizeof(standard)
                )
            )
            if standard.links != 1:
                raise OSError("The vault state contains a hardlinked file.")
        yield handle, directory
    finally:
        kernel.CloseHandle(handle)


def _tree(kernel: Any, security: Any, path: Path, sid: int) -> None:
    pending = list(path.iterdir())
    while pending:
        child = pending.pop()
        try:
            with _opened(kernel, child, root=False) as (handle, directory):
                _verify(kernel, security, handle, sid, directory=directory)
                if directory:
                    pending.extend(child.iterdir())
        except FileNotFoundError:
            continue


def _protect(security: Any, handle: Any, descriptor: Any) -> None:
    present, defaulted, acl = wintypes.BOOL(), wintypes.BOOL(), POINTER()
    _check(
        security.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)
        )
    )
    if not present or not acl.value:
        raise OSError("The private vault access list could not be constructed.")
    code = security.SetSecurityInfo(
        handle, 1, DACL_INFORMATION | PROTECTED_DACL_INFORMATION, None, None, acl, None
    )
    if code:
        raise _error(code)


def private(path: Path) -> None:
    kernel, security = _api()
    user = _user(kernel, security)
    sid = ctypes.cast(user, ctypes.POINTER(POINTER))[0]
    if sid is None:
        raise OSError("The current user has no valid Windows security identity.")
    descriptor = _descriptor(kernel, security, sid)
    try:
        path = path.absolute()
        path.parent.mkdir(parents=True, exist_ok=True)
        attributes = SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        if not kernel.CreateDirectoryW(str(path), ctypes.byref(attributes)):
            error = _error()
            if getattr(error, "winerror", None) != 183:
                raise error
        with _opened(kernel, path, root=True) as (handle, directory):
            protected = _verify(kernel, security, handle, sid, directory=directory)
            _tree(kernel, security, path, sid)
            if not protected:
                _protect(security, handle, descriptor)
                _tree(kernel, security, path, sid)
            if not _verify(kernel, security, handle, sid, directory=directory):
                raise OSError("The private vault access list still permits inheritance.")
    finally:
        kernel.LocalFree(descriptor)
