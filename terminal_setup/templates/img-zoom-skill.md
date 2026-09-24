---
name: img-zoom
description: Crop and magnify part of an image file to read fine detail. Use when an image (a screenshot, a dense chart, a technical drawing, a slide render, a scanned form) has small text, tight lines or labels you cannot read with confidence at the size you see it.
---

# img-zoom

`img-zoom` crops a box from the full-resolution original of an image file and magnifies it. Read the output file to see the region in detail.

## Rules

- **Get the original size first.** The image you see may be downscaled. Coordinates are pixels of the original.
- **Scale your coordinates.** When you see the image at a smaller size, multiply each coordinate by `original width / width you see`.
- **Check the printed crop box.** The command prints the image size and the box it cropped. Compare them with what you meant before you trust the result.
- **Zoom in steps.** Zoom a wide area, locate the detail, then zoom a smaller box inside it.
- **Leave `--scale` out.** By default the output takes the largest size a model reads at full detail.
- It works on image files only. It does not capture the screen.

## Commands

```bash
img-zoom --info drawing.png
img-zoom drawing.png 1200 800 1800 1100 -o /tmp/zoom.png
img-zoom drawing.png 1200 800 1800 1100 -o /tmp/zoom.png --scale 4
```

`--info` prints `WIDTH HEIGHT MODE`. A zoom prints the image size, the crop box and the output size.

## Measure and verify

The tool's Python has Pillow and OpenCV. It works offline, so use it for your own measuring scripts:

```bash
"$(uv tool dir)/img-zoom/bin/python" measure.py
```

## When it is missing

`img-zoom: command not found` means terminal-setup has not installed it on this machine. Re-run terminal-setup, or use `uv run --no-project --with pillow --with opencv-python-headless python` for a script.
