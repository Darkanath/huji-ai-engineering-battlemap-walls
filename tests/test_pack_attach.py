"""Tests for data/pack.py (Colab data pack), data/attach_image.py (hand-traced test maps) and
data/contact_sheet.py."""

import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from data.attach_image import attach_image, main, pixels_per_grid
from data.contact_sheet import dataset_sheets, grid
from data.manifest import read_manifest
from data.pack import build_pack
from data.rasterize import decode_image, load_uvtt

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"


def test_pack_holds_train_and_val_but_no_test(demo_processed: Path, tmp_path: Path) -> None:
    path = build_pack(demo_processed, tmp_path)
    assert path.name.startswith("data-") and path.suffix == ".zip"
    names = set(zipfile.ZipFile(path).namelist())
    rows = {r["map"]: r for r in read_manifest(demo_processed / "manifest.csv")}
    assert "manifest.csv" in names
    for name in ("syn0001", "dd01_a"):  # train, val
        assert {rows[name]["image_32"], rows[name]["mask_32"]} <= names
    assert not any("t01" in n for n in names)  # test never leaves the laptop
    assert not any("/32px/" not in n for n in names - {"manifest.csv"})  # 32 px copies only


def image_bytes(width: int, height: int, fmt: str = "JPEG") -> bytes:
    """An encoded blank image."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (90, 120, 60)).save(buf, format=fmt)
    return buf.getvalue()


def test_pixels_per_grid_rejects_images_not_cropped_to_the_grid() -> None:
    assert pixels_per_grid((1000, 600), {"x": 25, "y": 15}) == 40
    with pytest.raises(ValueError):
        pixels_per_grid((1010, 600), {"x": 25, "y": 15})  # not whole px per square
    with pytest.raises(ValueError):
        pixels_per_grid((1000, 640), {"x": 25, "y": 15})  # height doesn't match


def test_attach_image_embeds_the_original_and_sets_ppg(tmp_path: Path) -> None:
    uvtt = load_uvtt(DEMO_MAP)  # 25x25 squares
    out = attach_image(uvtt, image_bytes(1000, 1000))
    assert out["resolution"]["pixels_per_grid"] == 40
    assert out["line_of_sight"] == uvtt["line_of_sight"]
    assert decode_image(out, 40).size == (1000, 1000)
    assert uvtt["resolution"]["pixels_per_grid"] != 40  # the input is not changed

    target = tmp_path / "t01.dd2vtt"
    target.write_text(json.dumps(uvtt), encoding="utf-8")
    (tmp_path / "t01.png").write_bytes(image_bytes(500, 500, "PNG"))
    main([str(target), str(tmp_path / "t01.png")])
    written = load_uvtt(target)
    assert written["resolution"]["pixels_per_grid"] == 20
    assert base64.b64decode(written["image"]) == (tmp_path / "t01.png").read_bytes()

    (tmp_path / "bad.png").write_bytes(image_bytes(510, 500, "PNG"))
    with pytest.raises(SystemExit):
        main([str(target), str(tmp_path / "bad.png")])


def test_contact_sheets(demo_processed: Path, tmp_path: Path) -> None:
    sheet = grid([Image.new("RGB", (20, 10))] * 5, cols=2, labels=list("abcde"))
    assert sheet.width > 40 and sheet.height > 30
    written = dataset_sheets(demo_processed, tmp_path, None, thumb=50, cols=4)
    assert {p.name for p in written} == {
        "contact_sheet_synthetic.jpg",
        "contact_sheet_dungeondraft.jpg",
        "contact_sheet_test.jpg",
    }
