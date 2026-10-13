from __future__ import annotations

from collections.abc import Mapping
from email.message import Message
from http import HTTPStatus
from typing import BinaryIO

MAX_BODY_BYTES = 1_000_000
BODY_TIMEOUT_S = 10.0


class FramingError(ValueError):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def content_length(headers: Message | Mapping[str, str]) -> int:
    if headers.get("Transfer-Encoding") is not None:
        raise FramingError("Transfer-Encoding is unsupported; send one Content-Length")
    values = (
        headers.get_all("Content-Length", [])
        if isinstance(headers, Message)
        else ([headers["Content-Length"]] if "Content-Length" in headers else [])
    )
    if len(values) > 1:
        raise FramingError("send exactly one Content-Length header")
    raw = values[0].strip() if values else "0"
    if not raw.isascii() or not raw.isdecimal():
        raise FramingError("Content-Length must be a nonnegative decimal byte count")
    significant = raw.lstrip("0") or "0"
    if len(significant) > len(str(MAX_BODY_BYTES)) or int(significant) > MAX_BODY_BYTES:
        raise FramingError(
            f"the body is over {MAX_BODY_BYTES} bytes", HTTPStatus.REQUEST_ENTITY_TOO_LARGE
        )
    return int(significant)


def read_body(stream: BinaryIO, length: int) -> bytes:
    try:
        body = stream.read(length)
    except TimeoutError as error:
        raise FramingError("the request body timed out", HTTPStatus.REQUEST_TIMEOUT) from error
    if len(body) != length:
        raise FramingError("the request body ended before its Content-Length")
    return body
