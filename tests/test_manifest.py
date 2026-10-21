"""Tests for data/manifest.py: splits, processed outputs and the manifest CSV."""

import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from data.manifest import COLUMNS, assign_splits, build, parse_name, read_manifest
from data.rasterize import LIGHT_TIERS


def tiny_uvtt(seed: int | None = None) -> dict:
    """A 4x4-square map at 20 px per square: one wall, one door, one small light."""
    image = Image.new("RGB", (80, 80), (200, 180, 150))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    uvtt = {
        "format": 0.3,
        "resolution": {
            "map_origin": {"x": 0, "y": 0},
            "map_size": {"x": 4, "y": 4},
            "pixels_per_grid": 20,
        },
        "line_of_sight": [[{"x": 0, "y": 2}, {"x": 4, "y": 2}]],
        "portals": [{"bounds": [{"x": 1, "y": 2}, {"x": 2, "y": 2}]}],
        "lights": [{"position": {"x": 3, "y": 1}, "range": LIGHT_TIERS["small"]["range"]}],
        "image": base64.b64encode(buf.getvalue()).decode(),
    }
    if seed is not None:
        uvtt["generator"] = {"version": 1, "seed": seed}
    return uvtt


def write_maps(raw: Path, dataset: str, names: list[str], **kwargs) -> None:
    """Write tiny maps named `names` into raw/<dataset>/."""
    folder = raw / dataset
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / f"{name}.dd2vtt").write_text(json.dumps(tiny_uvtt(**kwargs)), encoding="utf-8")


@pytest.fixture
def raw(tmp_path: Path) -> Path:
    """A raw data folder: 5 Dungeondraft layouts (2 with variants), a DA map with its original,
    2 synthetic maps, a test map and the demo map's name."""
    raw = tmp_path / "raw"
    write_maps(raw, "dungeondraft", ["dd01_a", "dd01_b", "dd02_a", "dd02_b", "dd03_a", "dd04_a"])
    write_maps(raw, "dungeondraft", ["dd05_a", "demo-training-map"])
    write_maps(raw, "dungeon_alchemist", ["da01_a"])
    write_maps(raw / "dungeon_alchemist", "original", ["da01_a"])
    write_maps(raw, "synthetic", ["syn0001", "syn0002"], seed=1001)
    write_maps(raw, "test", ["t01"])
    return raw


def test_parse_name() -> None:
    """Layout and variant come from <layout>_<variant>; other names are their own layout."""
    assert parse_name("dd01_a") == ("dd01", "a")
    assert parse_name("da12_d") == ("da12", "d")
    assert parse_name("syn0001") == ("syn0001", "")
    assert parse_name("demo-training-map") == ("demo-training-map", "")


def test_variants_share_a_split(raw: Path, tmp_path: Path) -> None:
    """All variants of a layout get the same split."""
    rows = build(raw, tmp_path / "processed")
    by_layout: dict[str, set[str]] = {}
    for row in rows:
        by_layout.setdefault(row["layout"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in by_layout.values())


def test_original_folder_is_skipped(raw: Path, tmp_path: Path) -> None:
    """Only the top level of a dataset folder is read; original/ exports are not maps."""
    rows = build(raw, tmp_path / "processed")
    da = [r for r in rows if r["dataset"] == "dungeon_alchemist"]
    assert [r["map"] for r in da] == ["da01_a"]


def test_special_splits(raw: Path, tmp_path: Path) -> None:
    """test/ maps are always test; the demo map is a fixture outside every split."""
    rows = {r["map"]: r for r in build(raw, tmp_path / "processed")}
    assert rows["t01"]["split"] == "test"
    assert rows["demo-training-map"]["split"] == "fixture"
    assert rows["demo-training-map"]["dataset"] == "demo"


def test_real_datasets_get_val_and_test_layouts() -> None:
    """With 3+ layouts, a real-map dataset has a layout in val and in test; most are train."""
    splits = assign_splits("dungeondraft", [f"dd{i:02d}" for i in range(1, 14)], {}, seed=42)
    counts = {s: list(splits.values()).count(s) for s in ("train", "val", "test")}
    assert counts["val"] >= 1 and counts["test"] >= 1
    assert counts["train"] >= 8
    one = assign_splits("dungeon_alchemist", ["da01"], {}, seed=42)
    assert one == {"da01": "train"}


def test_same_seed_same_splits(raw: Path, tmp_path: Path) -> None:
    """Two builds from scratch with the same seed give the same splits."""
    a = {r["map"]: r["split"] for r in build(raw, tmp_path / "p1", seed=7)}
    b = {r["map"]: r["split"] for r in build(raw, tmp_path / "p2", seed=7)}
    assert a == b


def test_rebuild_keeps_existing_splits(raw: Path, tmp_path: Path) -> None:
    """Adding layouts and rebuilding never moves a layout that already has a split."""
    processed = tmp_path / "processed"
    before = {r["layout"]: r["split"] for r in build(raw, processed)}
    write_maps(raw, "dungeondraft", [f"dd{i:02d}_a" for i in range(6, 14)])
    after = {r["layout"]: r["split"] for r in build(raw, processed)}
    assert all(after[layout] == split for layout, split in before.items())


def test_rows_files_and_shares(raw: Path, tmp_path: Path) -> None:
    """Rows have every column, shares sum to 1, lights are counted, the 32 px copies exist."""
    processed = tmp_path / "processed"
    build(raw, processed)
    rows = read_manifest(processed / "manifest.csv")
    assert list(rows[0]) == COLUMNS
    row = next(r for r in rows if r["map"] == "dd01_a")
    shares = [float(row[f"share_{c}"]) for c in ("background", "wall", "portal", "light")]
    assert sum(shares) == pytest.approx(1.0, abs=1e-3)
    assert all(s > 0 for s in shares)
    assert (row["lights_small"], row["lights_medium"], row["lights_large"]) == ("1", "0", "0")
    assert np.array(Image.open(processed / row["mask_32"])).shape == (128, 128)  # 4 x 32 px
    assert Image.open(processed / row["image_32"]).size == (128, 128)
    assert Image.open(processed / row["image"]).size == (280, 280)  # 4 x 70 px
    synthetic = next(r for r in rows if r["map"] == "syn0001")
    assert synthetic["seed"] == "1001"
