from __future__ import annotations

import sys

from PIL import Image, UnidentifiedImageError

from img_zoom.geometry import BoxError
from img_zoom.request import InfoRequest, PythonRequest, parse_request, plan_zoom, zoom_report


def main(argv: list[str] | None = None) -> int:
    request = parse_request(argv)
    if isinstance(request, PythonRequest):
        print(sys.executable)
        return 0
    try:
        with Image.open(request.image) as image:
            width, height = image.size
            if isinstance(request, InfoRequest):
                print(f"{width} {height} {image.mode}")
                return 0
            plan = plan_zoom(width, height, request)
            cropped = image.crop(plan.box)
            zoomed = cropped.resize(plan.size, Image.Resampling.LANCZOS)
            zoomed.save(request.output, format="PNG")
            mode = image.mode
    except (FileNotFoundError, UnidentifiedImageError) as error:
        print(f"img-zoom: cannot read {request.image} as an image: {error}", file=sys.stderr)
        return 2
    except BoxError as error:
        print(f"img-zoom: {error}", file=sys.stderr)
        return 2
    for line in zoom_report(width, height, mode, plan, request.output):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
