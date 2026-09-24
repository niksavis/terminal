from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from img_zoom.geometry import Box, fit_size, scaled_size, validate_box, within_budget

USAGE = "img-zoom IMAGE X1 Y1 X2 Y2 -o OUT.png [--scale N]\n       img-zoom --info IMAGE"


@dataclass(frozen=True)
class InfoRequest:
    image: Path


@dataclass(frozen=True)
class ZoomRequest:
    image: Path
    box: Box
    output: Path
    scale: float | None


@dataclass(frozen=True)
class ZoomPlan:
    box: Box
    size: tuple[int, int]
    over_budget: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="img-zoom",
        usage=USAGE,
        description=(
            "Crop a box from an image file at full resolution and magnify it. "
            "Coordinates are pixels of the original image, origin at the top-left corner."
        ),
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("coords", nargs="*", type=int, metavar="X1 Y1 X2 Y2")
    parser.add_argument("-o", "--output", type=Path, help="PNG file to write")
    parser.add_argument(
        "--scale",
        type=float,
        help="magnify by this factor instead of fitting the largest readable size",
    )
    parser.add_argument("--info", action="store_true", help="print width, height and mode")
    return parser


def parse_request(argv: list[str] | None = None) -> InfoRequest | ZoomRequest:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.info:
        if args.coords or args.output or args.scale is not None:
            parser.error("--info takes only IMAGE")
        return InfoRequest(args.image)
    if len(args.coords) != 4:
        parser.error(f"expected 4 coordinates X1 Y1 X2 Y2, got {len(args.coords)}")
    if args.output is None:
        parser.error("-o OUT.png is required")
    if args.output.suffix.lower() != ".png":
        parser.error(f"-o must name a .png file, got {args.output}")
    if args.output.resolve() == args.image.resolve():
        parser.error("-o must not overwrite the input image")
    return ZoomRequest(args.image, Box(*args.coords), args.output, args.scale)


def plan_zoom(width: int, height: int, request: ZoomRequest) -> ZoomPlan:
    box = validate_box(width, height, request.box)
    if request.scale is None:
        size = fit_size(box.width, box.height)
    else:
        size = scaled_size(box.width, box.height, request.scale)
    return ZoomPlan(box, size, not within_budget(*size))


def zoom_report(width: int, height: int, mode: str, plan: ZoomPlan, output: Path) -> list[str]:
    box = plan.box
    factor = plan.size[0] / box.width
    lines = [
        f"image: {width}x{height} {mode}",
        f"crop: ({box.x1},{box.y1})-({box.x2},{box.y2}) = {box.width}x{box.height} px",
        f"output: {plan.size[0]}x{plan.size[1]} px (x{factor:.2f}) -> {output}",
    ]
    if plan.over_budget:
        lines.append(
            "warning: the output exceeds what a model sees at full detail; "
            "the reader will downscale it. Drop --scale or crop a smaller box."
        )
    return lines
