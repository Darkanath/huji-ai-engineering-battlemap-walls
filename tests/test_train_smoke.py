"""Smoke tests for train/train.py on the demo map, on the CPU: training steps, the learning-rate
schedule, a short run with all its outputs, and resuming."""

import copy
import csv
from pathlib import Path

import pytest
import torch

from train.dataset import CropDataset, load_maps, select_rows
from train.losses import SegLoss
from train.model import build_model
from train.train import (
    learning_rates,
    load_config,
    make_optimizer,
    pick_showcase,
    run,
    train_step,
)

CONFIG = Path(__file__).parents[1] / "train/configs/stage1_synthetic.toml"


def tiny_config(processed: Path, run_name: str) -> dict:
    """The stage 1 config, shrunk to seconds on the CPU, without a weight download."""
    cfg = copy.deepcopy(load_config(CONFIG))
    cfg["run_name"] = run_name
    cfg["data"]["manifest"] = str(processed / "manifest.csv")
    cfg["data"]["crops_per_epoch"] = 4
    cfg["model"]["encoder_weights"] = ""
    cfg["train"].update(epochs=3, batch_size=2, freeze_encoder_epochs=1, early_stop_patience=5)
    cfg["runtime"].update(device="cpu", workers=0, threads=2, channels_last=False)
    return cfg


def test_two_steps_lower_the_loss(demo_processed: Path) -> None:
    from data.manifest import read_manifest

    torch.manual_seed(0)
    rows = select_rows(read_manifest(demo_processed / "manifest.csv"), "train", ["synthetic"])
    dataset = CropDataset(load_maps(demo_processed, rows, 256), crops_per_epoch=2, seed=0)
    images, masks = zip(*(dataset[i] for i in range(2)), strict=True)
    images, masks = torch.stack(images), torch.stack(masks)

    model = build_model(encoder_weights=None)
    model.train()
    t = {"lr_decoder": 1e-3, "lr_encoder": 1e-3, "weight_decay": 0.0}
    optimizer = make_optimizer(model, t)
    loss_fn = SegLoss([1.0, 4.0, 13.0, 20.0])
    device = torch.device("cpu")
    first = train_step(model, images, masks, loss_fn, optimizer, device)
    for _ in range(4):
        last = train_step(model, images, masks, loss_fn, optimizer, device)
    assert last < first


def test_learning_rate_schedule() -> None:
    t = {
        "epochs": 30,
        "freeze_encoder_epochs": 5,
        "warmup_epochs": 1,
        "lr_decoder": 1e-3,
        "lr_encoder": 1e-4,
        "min_lr": 1e-6,
    }
    assert learning_rates(2.5, t) == (1e-3, 0.0)  # frozen: decoder only
    decoder, encoder = learning_rates(5.5, t)  # half-way through the encoder warmup
    assert encoder == pytest.approx(0.5 * learning_rates(6.0, t)[1], rel=0.01)
    assert decoder < 1e-3
    assert learning_rates(30.0, t) == pytest.approx((1e-6, 1e-6))
    stage2 = {**t, "freeze_encoder_epochs": 0, "lr_decoder": 1e-4, "lr_encoder": 1e-5}
    assert learning_rates(0.0, stage2) == pytest.approx((1e-4, 1e-5))  # no warmup


def test_pick_showcase_prefers_real_maps_and_distinct_layouts() -> None:
    rows = [
        {"dataset": d, "map": f"{layout}_{v}", "layout": layout, "variant": v}
        for d, layouts in (
            ("dungeondraft", ["dd01", "dd02"]),
            ("dungeon_alchemist", ["da01"]),
            ("synthetic", ["syn1", "syn2", "syn3"]),
        )
        for layout in layouts
        for v in ("a", "b")
    ]
    picked = pick_showcase(rows, 6)
    assert picked[:3] == ["dd01_a", "da01_a", "dd02_a"]
    assert len(picked) == 6 and len(set(picked)) == 6


def test_short_run_writes_outputs_and_resumes_to_the_same_model(
    demo_processed: Path, tmp_path: Path
) -> None:
    # Straight through: 2 epochs.
    straight = run(tiny_config(demo_processed, "straight"), tmp_path, max_epochs=2)
    for name in ("best.pt", "last.pt", "metrics.csv"):
        assert (straight / name).exists()
    with open(straight / "metrics.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["epoch"] for r in rows] == ["1", "2"]
    assert "val_real/boundary_f1_wall" in rows[0] and "crop_share/wall" in rows[0]
    assert (straight / "predictions" / "epoch_02" / "dd01_a.jpg").exists()
    assert (tmp_path / "mlruns").exists()

    # Stopped after 1 epoch, then resumed for 1 more: same weights as straight through.
    cfg = tiny_config(demo_processed, "resumed")
    run(cfg, tmp_path, max_epochs=1)
    with pytest.raises(FileExistsError):
        run(cfg, tmp_path, max_epochs=1)  # no silent overwrite without --resume
    resumed = run(cfg, tmp_path, resume=True, max_epochs=1)

    a = torch.load(straight / "last.pt", weights_only=False)
    b = torch.load(resumed / "last.pt", weights_only=False)
    assert a["epoch"] == b["epoch"] == 2
    for key, value in a["model"].items():
        assert torch.allclose(value.float(), b["model"][key].float(), atol=1e-6), key
