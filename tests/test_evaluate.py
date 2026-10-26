"""Tests for eval/evaluate.py: running a predictor over a manifest split."""

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from data.manifest import build
from eval.evaluate import evaluate, select_rows, summarize, unet, write_csv
from train.model import build_model

DEMO_MAP = Path(__file__).parents[1] / "data/raw/dungeondraft/demo-training-map.dd2vtt"


def test_scores_per_map_and_means(tmp_path: Path) -> None:
    """A predictor that returns the true mask scores 1 on the map and in every mean row."""
    raw = tmp_path / "raw" / "dungeondraft"
    raw.mkdir(parents=True)
    uvtt = json.loads(DEMO_MAP.read_text(encoding="utf-8"))
    (raw / "dd01_a.dd2vtt").write_text(json.dumps(uvtt), encoding="utf-8")
    processed = tmp_path / "processed"
    build(tmp_path / "raw", processed)

    rows = select_rows(processed / "manifest.csv", "train")
    assert [r["map"] for r in rows] == ["dd01_a"]
    true = np.array(Image.open(processed / rows[0]["mask_32"]))
    results = evaluate(processed, rows, lambda image, ppg: true)
    assert results[0]["boundary_f1_wall"] == 1.0
    assert results[0]["iou_portal"] == 1.0

    summary = summarize(results)
    assert [s["dataset"] for s in summary] == ["dungeondraft", "real", "all"]
    assert all(s["iou_wall"] == 1.0 for s in summary)
    write_csv(tmp_path / "metrics.csv", results + summary)
    assert (tmp_path / "metrics.csv").read_text().count("\n") == 5  # header + 1 map + 3 means


def test_unet_checkpoint_predictor(tmp_path: Path) -> None:
    """A saved checkpoint loads as a predictor and returns a full-size class mask."""

    cfg = {"model": {"arch": "unet", "encoder": "resnet18"}, "val": {"window": 256, "stride": 192}}
    path = tmp_path / "best.pt"
    torch.save({"model": build_model(encoder_weights=None).state_dict(), "config": cfg}, path)
    mask = unet(path)(np.zeros((300, 280, 3), np.uint8), 32)
    assert mask.shape == (300, 280) and mask.max() <= 3
