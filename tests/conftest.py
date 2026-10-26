"""Shared fixtures: a small processed dataset built from the demo map."""

import csv
import shutil
from pathlib import Path

import pytest

from data.manifest import build, read_manifest

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"


@pytest.fixture(scope="session")
def demo_processed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """data/processed-style folder with the demo map three times: syn0001 in train, syn0002 in
    val (as a Dungeondraft map, so it counts as real val) and t01 in test."""
    root = tmp_path_factory.mktemp("demo_data")
    raw, processed = root / "raw", root / "processed"
    for dataset, name in (("synthetic", "syn0001"), ("dungeondraft", "dd01_a"), ("test", "t01")):
        (raw / dataset).mkdir(parents=True, exist_ok=True)
        shutil.copy(DEMO_MAP, raw / dataset / f"{name}.dd2vtt")
    build(raw, processed)

    # One map per dataset can't fill every split by itself, so set the splits by hand.
    manifest = processed / "manifest.csv"
    rows = read_manifest(manifest)
    splits = {"syn0001": "train", "dd01_a": "val", "t01": "test"}
    for row in rows:
        row["split"] = splits[row["map"]]
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return processed
