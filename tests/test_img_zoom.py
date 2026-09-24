from __future__ import annotations

from pathlib import Path

import pytest
from img_zoom.cli import main
from img_zoom.geometry import (
    MAX_EDGE,
    MAX_PATCHES,
    Box,
    BoxError,
    fit_size,
    patches,
    scaled_size,
    validate_box,
    within_budget,
)
from img_zoom.request import InfoRequest, ZoomRequest, parse_request, plan_zoom, zoom_report
from PIL import Image


def test_patches_counts_partial_tiles() -> None:
    assert patches(28, 28) == 1
    assert patches(29, 28) == 2
    assert patches(56, 57) == 6


@pytest.mark.parametrize(
    ("width", "height"),
    [(10, 10), (800, 500), (500, 800), (37, 1), (1, 37), (4000, 3000), (123, 457), (3, 2000)],
)
def test_fit_size_stays_within_budget_and_keeps_aspect(width: int, height: int) -> None:
    fitted = fit_size(width, height)
    assert within_budget(*fitted)
    assert (
        abs(fitted[0] / fitted[1] - width / height)
        <= max(1 / fitted[0], 1 / fitted[1]) * (width / height) + 1e-9
    )


@pytest.mark.parametrize(("width", "height"), [(10, 10), (800, 500), (640, 480), (100, 20)])
def test_fit_size_is_the_largest_size_within_budget(width: int, height: int) -> None:
    fitted = fit_size(width, height)
    long_edge = max(fitted)
    grown = (
        (long_edge + 1, round(height * (long_edge + 1) / width))
        if width >= height
        else (round(width * (long_edge + 1) / height), long_edge + 1)
    )
    assert not within_budget(*grown)


def test_fit_size_of_a_wide_strip_is_capped_by_the_edge() -> None:
    assert fit_size(1000, 100) == (MAX_EDGE, 258)


def test_fit_size_of_a_square_is_capped_by_the_patch_budget() -> None:
    width, height = fit_size(100, 100)
    assert width == height
    assert patches(width, height) <= MAX_PATCHES < patches(width + 28, height + 28)


def test_fit_size_shrinks_a_crop_larger_than_the_budget() -> None:
    assert max(fit_size(6000, 4000)) < 6000


def test_validate_box_accepts_the_full_image() -> None:
    assert validate_box(640, 480, Box(0, 0, 640, 480)) == Box(0, 0, 640, 480)


@pytest.mark.parametrize(
    "box",
    [
        Box(-1, 0, 10, 10),
        Box(10, 10, 10, 20),
        Box(20, 10, 10, 20),
        Box(0, 20, 10, 10),
        Box(0, 0, 641, 10),
        Box(0, 0, 10, 481),
    ],
)
def test_validate_box_refuses_and_names_the_image_size(box: Box) -> None:
    with pytest.raises(BoxError, match="640x480"):
        validate_box(640, 480, box)


def test_scaled_size_multiplies_and_refuses_non_positive() -> None:
    assert scaled_size(100, 50, 2.5) == (250, 125)
    assert scaled_size(3, 1, 0.1) == (1, 1)
    with pytest.raises(BoxError, match="greater than 0"):
        scaled_size(100, 50, 0)


def test_parse_request_reads_a_zoom(tmp_path: Path) -> None:
    image = tmp_path / "in.png"
    output = tmp_path / "out.png"
    request = parse_request([str(image), "1", "2", "30", "40", "-o", str(output)])
    assert request == ZoomRequest(image, Box(1, 2, 30, 40), output, None)


def test_parse_request_reads_info(tmp_path: Path) -> None:
    assert parse_request(["--info", str(tmp_path / "in.png")]) == InfoRequest(tmp_path / "in.png")


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["1", "2", "3", "-o", "out.png"], "expected 4 coordinates"),
        (["1", "2", "3", "4"], "-o OUT.png is required"),
        (["1", "2", "3", "4", "-o", "out.jpg"], "must name a .png"),
        (["1", "2", "3", "4", "-o", "in.png"], "must not overwrite"),
        (["--info", "1", "2", "3", "4"], "--info takes only IMAGE"),
    ],
)
def test_parse_request_refuses_by_name(
    extra: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        parse_request(["in.png", *extra])
    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err


def test_plan_zoom_fits_by_default_and_flags_an_oversized_scale(tmp_path: Path) -> None:
    fitted = plan_zoom(1000, 1000, ZoomRequest(tmp_path, Box(0, 0, 100, 100), tmp_path, None))
    assert fitted.size == fit_size(100, 100)
    assert not fitted.over_budget
    scaled = plan_zoom(1000, 1000, ZoomRequest(tmp_path, Box(0, 0, 100, 100), tmp_path, 40))
    assert scaled.size == (4000, 4000)
    assert scaled.over_budget


def test_zoom_report_prints_image_size_crop_box_and_output(tmp_path: Path) -> None:
    plan = plan_zoom(4000, 3000, ZoomRequest(tmp_path, Box(100, 200, 900, 700), tmp_path, 2))
    lines = zoom_report(4000, 3000, "RGB", plan, Path("out.png"))
    assert lines == [
        "image: 4000x3000 RGB",
        "crop: (100,200)-(900,700) = 800x500 px",
        "output: 1600x1000 px (x2.00) -> out.png",
    ]


def _marked_image(path: Path) -> Path:
    image = Image.new("RGB", (400, 300), "white")
    image.paste((255, 0, 0), (100, 50, 140, 70))
    image.save(path)
    return path


def test_main_zooms_the_box_from_the_original(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _marked_image(tmp_path / "in.png")
    output = tmp_path / "out.png"

    assert main([str(source), "100", "50", "140", "70", "-o", str(output)]) == 0

    with Image.open(output) as zoomed:
        assert zoomed.size == fit_size(40, 20)
        assert zoomed.getpixel((zoomed.width // 2, zoomed.height // 2)) == (255, 0, 0)
    assert capsys.readouterr().out.splitlines()[:2] == [
        "image: 400x300 RGB",
        "crop: (100,50)-(140,70) = 40x20 px",
    ]


def test_main_info_prints_width_height_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _marked_image(tmp_path / "in.png")

    assert main(["--info", str(source)]) == 0
    assert capsys.readouterr().out == "400 300 RGB\n"


def test_main_refuses_a_box_outside_the_image_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _marked_image(tmp_path / "in.png")
    output = tmp_path / "out.png"

    assert main([str(source), "0", "0", "401", "10", "-o", str(output)]) == 2
    assert not output.exists()
    assert "400x300" in capsys.readouterr().err


def test_main_refuses_a_file_that_is_not_an_image(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("not an image", encoding="utf-8")

    assert main([str(source), "0", "0", "1", "1", "-o", str(tmp_path / "out.png")]) == 2
    assert "cannot read" in capsys.readouterr().err
