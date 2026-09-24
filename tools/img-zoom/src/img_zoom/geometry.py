from __future__ import annotations

import math
from typing import NamedTuple

MAX_EDGE = 2576
MAX_PATCHES = 4784
PATCH = 28


class Box(NamedTuple):
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


class BoxError(ValueError):
    pass


def patches(width: int, height: int) -> int:
    return math.ceil(width / PATCH) * math.ceil(height / PATCH)


def within_budget(width: int, height: int) -> bool:
    return max(width, height) <= MAX_EDGE and patches(width, height) <= MAX_PATCHES


def validate_box(width: int, height: int, box: Box) -> Box:
    size = f"the image is {width}x{height} px, so x must be 0..{width} and y 0..{height}"
    if min(box) < 0:
        raise BoxError(f"negative coordinate in {tuple(box)}: {size}")
    if box.x2 <= box.x1 or box.y2 <= box.y1:
        raise BoxError(f"x2 must exceed x1 and y2 must exceed y1, got {tuple(box)}: {size}")
    if box.x2 > width or box.y2 > height:
        raise BoxError(f"box {tuple(box)} reaches outside the image: {size}")
    return box


def fit_size(width: int, height: int) -> tuple[int, int]:
    long_edge = max(width, height)
    by_edge = MAX_EDGE / long_edge
    by_patches = math.sqrt(MAX_PATCHES * PATCH * PATCH / (width * height))
    target = math.floor(long_edge * min(by_edge, by_patches))
    while target > 1:
        size = _scaled_to_long_edge(width, height, target)
        if within_budget(*size):
            return size
        target -= 1
    return _scaled_to_long_edge(width, height, 1)


def scaled_size(width: int, height: int, scale: float) -> tuple[int, int]:
    if scale <= 0:
        raise BoxError(f"--scale must be greater than 0, got {scale}")
    return max(1, round(width * scale)), max(1, round(height * scale))


def _scaled_to_long_edge(width: int, height: int, long_edge: int) -> tuple[int, int]:
    if width >= height:
        return long_edge, max(1, round(height * long_edge / width))
    return max(1, round(width * long_edge / height)), long_edge
