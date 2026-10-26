"""Train a U-Net on 256×256 crops and select the best epoch on whole validation maps.

Everything follows docs/training.md; the run is described by one TOML config
(train/configs/*.toml, §11):

- **Data** (§2): training crops from the training split of `data.train` (train/dataset.py);
  validation on the whole val maps of `data.val`, at 32 px per square.
- **Model** (§1, §5): U-Net, encoder frozen for the first `freeze_encoder_epochs` (decoder
  only), then the whole network. AdamW with one learning rate for the decoder and one for the
  encoder; after unfreezing, the encoder warms up linearly, then both follow a cosine decay to
  `min_lr`. Gradients are clipped.
- **Loss** (§4): weighted cross-entropy + Dice (train/losses.py), class weights from the
  training split's pixel shares in the manifest.
- **Validation** (§6) every epoch: sliding-window inference (train/predict.py), validation loss,
  IoU and F1 per class and wall boundary F1 per dataset, for the real maps pooled and for all.
  The best epoch is the one with the highest wall boundary F1 on the `select_on` datasets
  (ties: higher portal IoU); early stopping after `early_stop_patience` epochs without one.
- **Outputs** (§9) in `<runs>/<run_name>/`: `best.pt`, `last.pt` (written every epoch, with
  everything needed to resume), a copy of the config, `metrics.csv` (one row per epoch) and
  `predictions/epoch_NN/` (image | truth | prediction for 6 fixed validation maps). Everything
  is also logged to MLflow in `<runs>/mlruns`: the config, git commit, manifest hash, device,
  per-epoch metrics and the artifacts.

Usage:
  python -m train.train --config train/configs/stage1_synthetic.toml [--runs runs]
                        [--processed data/processed] [--resume]
"""

import argparse
import csv
import math
import os
import random
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

import mlflow
import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader

from data.manifest import read_manifest
from data.pack import manifest_hash
from data.rasterize import overlay
from eval.evaluate import REAL, summarize
from eval.metrics import mean_scores, score
from train.dataset import CropDataset, load_maps, select_rows
from train.losses import SegLoss, class_weights, split_shares
from train.model import (
    autocast_dtype,
    build_model,
    device_name,
    pick_device,
    set_encoder_frozen,
    setup_cpu,
    train_mode,
)
from train.predict import predict_probs

# MLflow 3 keeps its plain-file tracking store (runs/mlruns) only on request. Plain files suit
# this project: on Colab the runs folder is on Google Drive, where an SQLite database is
# unreliable, and the folder copies back to the laptop as it is.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

ROOT = Path(__file__).parents[1]
EXPERIMENT = "battlemap-walls"
SHOWCASE_MAPS = 6  # validation maps whose predictions are saved every epoch
PPG = 32


# ---------------------------------------------------------------- config and setup


def load_config(path: Path) -> dict:
    """Read a run config (TOML)."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def flatten(cfg: dict, prefix: str = "") -> dict[str, str]:
    """A nested config as flat "section.key" -> str pairs, for MLflow params."""
    out = {}
    for key, value in cfg.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, f"{name}."))
        else:
            out[name] = str(value)
    return out


def seed_everything(seed: int) -> None:
    """Seed `random`, `numpy` and `torch` (crops and augmentation have their own seeds)."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def git_commit() -> str:
    """The current git commit, or "unknown" outside a git checkout."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def resolve_run_path(path: str, runs: Path) -> Path:
    """A path from the config such as "runs/r1/best.pt", moved under `runs` (Drive on Colab)."""
    p = Path(path)
    if not p.is_absolute() and p.parts and p.parts[0] == "runs":
        return runs.joinpath(*p.parts[1:])
    return p


# ---------------------------------------------------------------- optimization


def make_optimizer(model: nn.Module, t: dict) -> torch.optim.Optimizer:
    """AdamW with two parameter groups: 0 = decoder and head, 1 = encoder."""
    encoder = list(model.encoder.parameters())
    encoder_ids = {id(p) for p in encoder}
    decoder = [p for p in model.parameters() if id(p) not in encoder_ids]
    return torch.optim.AdamW(
        [{"params": decoder, "lr": t["lr_decoder"]}, {"params": encoder, "lr": t["lr_encoder"]}],
        weight_decay=t["weight_decay"],
    )


def learning_rates(epoch: float, t: dict) -> tuple[float, float]:
    """(decoder, encoder) learning rates at a fractional `epoch` (0-based).

    While the encoder is frozen the decoder trains at `lr_decoder`. From unfreezing to the last
    epoch, both decay along a cosine to `min_lr`; the encoder first warms up linearly over
    `warmup_epochs` (only when it was frozen before).
    """
    freeze = t.get("freeze_encoder_epochs", 0)
    if epoch < freeze:
        return t["lr_decoder"], 0.0
    since = epoch - freeze
    progress = min(1.0, since / max(1, t["epochs"] - freeze))
    cosine = 0.5 * (1 + math.cos(math.pi * progress))
    min_lr = t["min_lr"]
    decoder = min_lr + (t["lr_decoder"] - min_lr) * cosine
    encoder = min_lr + (t["lr_encoder"] - min_lr) * cosine
    warmup = t.get("warmup_epochs", 0)
    if freeze > 0 and warmup > 0 and since < warmup:
        encoder *= since / warmup
    return decoder, encoder


def set_learning_rates(optimizer: torch.optim.Optimizer, rates: tuple[float, float]) -> None:
    """Set the decoder and encoder group learning rates."""
    for group, lr in zip(optimizer.param_groups, rates, strict=True):
        group["lr"] = lr


def train_step(
    model: nn.Module,
    images: torch.Tensor,
    masks: torch.Tensor,
    loss_fn: SegLoss,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    amp_dtype: torch.dtype | None = None,
    scaler: torch.amp.GradScaler | None = None,
    grad_clip: float = 1.0,
    channels_last: bool = False,
) -> float:
    """One optimization step on a batch; returns the loss."""
    memory_format = torch.channels_last if channels_last else torch.contiguous_format
    images = images.to(device, memory_format=memory_format, non_blocking=True)
    masks = masks.to(device, non_blocking=True)
    optimizer.zero_grad(set_to_none=True)
    with torch.autocast(device.type, dtype=amp_dtype, enabled=amp_dtype is not None):
        logits = model(images)
    loss = loss_fn(logits, masks)
    if scaler is not None:
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
    else:
        loss.backward()
    if grad_clip:
        nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
    if scaler is not None:
        scaler.step(optimizer)
        scaler.update()
    else:
        optimizer.step()
    return float(loss.detach())


# ---------------------------------------------------------------- validation


def selection_key(metrics: dict[str, float]) -> tuple[float, float]:
    """(wall boundary F1, portal IoU), higher is better; NaN counts as -1."""

    def value(key: str) -> float:
        v = metrics.get(key, math.nan)
        return -1.0 if math.isnan(v) else v

    return value("boundary_f1_wall"), value("iou_portal")


def interleave(groups: list[list[dict]]) -> list[dict]:
    """Rows taken from each group in turn: a1, b1, a2, b2, ..."""
    out = []
    for i in range(max((len(g) for g in groups), default=0)):
        out += [g[i] for g in groups if i < len(g)]
    return out


def pick_showcase(rows: list[dict], count: int = SHOWCASE_MAPS) -> list[str]:
    """Names of `count` fixed validation maps for the prediction images.

    Real maps first, alternating between the tools; within a tool one map per layout before a
    second variant of any layout. Other datasets (synthetic) only fill the remaining places.
    """
    by_dataset: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda r: (r["variant"], r["map"])):
        by_dataset.setdefault(row["dataset"], []).append(row)

    def layouts_first(group: list[dict]) -> list[dict]:
        """One row per layout first, then the other variants."""
        first, rest, seen = [], [], set()
        for row in group:
            (rest if row["layout"] in seen else first).append(row)
            seen.add(row["layout"])
        return first + rest

    real = [layouts_first(by_dataset[d]) for d in REAL if d in by_dataset]
    other = [layouts_first(g) for d, g in sorted(by_dataset.items()) if d not in REAL]
    return [row["map"] for row in interleave(real) + interleave(other)][:count]


def showcase_image(image: np.ndarray, true: np.ndarray, pred: np.ndarray) -> Image.Image:
    """Image | ground truth overlay | prediction overlay, side by side."""
    base = Image.fromarray(image)
    panels = [base, overlay(base, true), overlay(base, pred)]
    out = Image.new("RGB", (base.width * 3, base.height))
    for i, panel in enumerate(panels):
        out.paste(panel, (i * base.width, 0))
    return out


def validate(
    model: nn.Module,
    val_maps: list[tuple[dict, np.ndarray, np.ndarray]],
    loss_fn: SegLoss,
    device: torch.device,
    v: dict,
    channels_last: bool = False,
) -> tuple[list[dict], dict[str, np.ndarray]]:
    """Score every validation map; returns per-map result rows (loss and metrics) and the
    predicted masks by map name."""
    results, preds = [], {}
    loss_fn = loss_fn.cpu()
    for row, image, true in val_maps:
        probs = predict_probs(
            model, image, device, v["window"], v["stride"], channels_last=channels_last
        )
        target = torch.from_numpy(true).long()
        loss = float(loss_fn.from_probs(probs[None], target[None]))
        pred = probs.argmax(dim=0).numpy().astype(np.uint8)
        ids = {k: row[k] for k in ("dataset", "map", "layout", "split")}
        results.append({**ids, "loss": loss, **score(pred, true, PPG)})
        preds[row["map"]] = pred
    loss_fn.to(device)
    return results, preds


# ---------------------------------------------------------------- logging


def append_metrics_csv(path: Path, row: dict) -> None:
    """Append one epoch's row to metrics.csv, keeping the header of an existing file."""
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            fieldnames = next(csv.reader(f))
    else:
        fieldnames = list(row)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if f.tell() == 0:
            writer.writeheader()
        writer.writerow({k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()})


def finite(metrics: dict[str, float]) -> dict[str, float]:
    """Only the finite values (MLflow gets no NaN)."""
    return {k: v for k, v in metrics.items() if isinstance(v, float) and math.isfinite(v)}


# ---------------------------------------------------------------- the run


def run(
    cfg: dict,
    runs: Path,
    processed: Path | None = None,
    resume: bool = False,
    config_path: Path | None = None,
    max_epochs: int | None = None,
) -> Path:
    """Train one run from `cfg`; returns its run folder.

    `processed` defaults to the manifest's folder. `max_epochs` stops after that many epochs in
    this call (for tests and short checks); the schedule still follows `train.epochs`.
    """
    data_cfg, model_cfg, t, loss_cfg, v, rt = (
        cfg["data"],
        cfg["model"],
        cfg["train"],
        cfg["loss"],
        cfg["val"],
        cfg["runtime"],
    )
    processed = processed or Path(data_cfg["manifest"]).parent
    manifest = processed / "manifest.csv"
    run_dir = runs / cfg["run_name"]
    last_path, best_path = run_dir / "last.pt", run_dir / "best.pt"
    if last_path.exists() and not resume:
        raise FileExistsError(f"{run_dir} already has a run; pass --resume or pick a new run_name")

    seed_everything(cfg["seed"])
    device = pick_device(rt["device"])
    if device.type == "cpu":
        setup_cpu(rt["threads"])
    amp_dtype = autocast_dtype(device, rt["precision"])
    channels_last = bool(rt.get("channels_last", False))

    # Data
    rows = read_manifest(manifest)
    train_rows = select_rows(rows, "train", data_cfg["train"])
    val_rows = select_rows(rows, "val", data_cfg["val"])
    if not train_rows or not val_rows:
        raise ValueError(f"need train and val maps; found {len(train_rows)} and {len(val_rows)}")
    crop = data_cfg["crop_size"]
    train_set = CropDataset(
        load_maps(processed, train_rows, crop),
        data_cfg["crops_per_epoch"],
        crop,
        data_cfg["crop_bias"],
        cfg["seed"],
    )
    val_maps = [
        (row, data.image, data.mask)
        for row, data in zip(val_rows, load_maps(processed, val_rows), strict=True)
    ]
    showcase = pick_showcase(val_rows)
    select_on = set(data_cfg.get("select_on") or data_cfg["val"])
    if not any(row["dataset"] in select_on for row in val_rows):
        select_on = {row["dataset"] for row in val_rows}  # e.g. no real val maps yet
    loader = DataLoader(
        train_set,
        batch_size=t["batch_size"],
        shuffle=False,  # the crops are already in a seeded random order
        num_workers=rt["workers"],
        pin_memory=device.type == "cuda",
        drop_last=True,
    )

    # Model, loss, optimizer
    model = build_model(model_cfg["arch"], model_cfg["encoder"], model_cfg["encoder_weights"])
    if model_cfg.get("init_checkpoint"):
        init_path = resolve_run_path(model_cfg["init_checkpoint"], runs)
        init = torch.load(init_path, map_location="cpu", weights_only=False)
        model.load_state_dict(init["model"])
    model.to(device)
    if channels_last:
        model.to(memory_format=torch.channels_last)
    weights = class_weights(split_shares(train_rows), loss_cfg["class_weight_cap"])
    loss_fn = SegLoss(weights, loss_cfg["ce_weight"], loss_cfg["dice_weight"]).to(device)
    optimizer = make_optimizer(model, t)
    scaler = torch.amp.GradScaler("cuda") if amp_dtype == torch.float16 else None

    # State, fresh or resumed
    start_epoch, best, best_epoch, since_best, mlflow_run_id = 0, None, 0, 0, None
    if resume and last_path.exists():
        state = torch.load(last_path, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        if scaler is not None and state.get("scaler"):
            scaler.load_state_dict(state["scaler"])
        start_epoch, best_epoch = state["epoch"], state["best_epoch"]
        since_best = state["since_best"]
        best = tuple(state["best"]) if state["best"] is not None else None
        mlflow_run_id = state["mlflow_run_id"]
        random.setstate(state["python_rng"])
        np.random.set_state(state["numpy_rng"])
        torch.set_rng_state(state["torch_rng"])
        print(f"resuming {cfg['run_name']} after epoch {start_epoch}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if config_path is not None and not (run_dir / "config.toml").exists():
        shutil.copy(config_path, run_dir / "config.toml")

    mlflow.set_tracking_uri((runs / "mlruns").resolve().as_uri())
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_id=mlflow_run_id, run_name=cfg["run_name"]) as active:
        if mlflow_run_id is None:
            mlflow.log_params(flatten(cfg))
            mlflow.log_params(
                {
                    "git_commit": git_commit(),
                    "manifest_hash": manifest_hash(manifest),
                    "device": device.type,
                    "device_name": device_name(device),
                    "precision": str(amp_dtype or torch.float32).replace("torch.", ""),
                    "torch_version": torch.__version__,
                    "train_maps": len(train_rows),
                    "val_maps": len(val_rows),
                    "class_weights": ", ".join(f"{w:.2f}" for w in weights),
                    "showcase_maps": ", ".join(showcase),
                }
            )
            if config_path is not None:
                mlflow.log_artifact(str(config_path))
        print(
            f"{cfg['run_name']}: {len(train_rows)} train maps, {len(val_rows)} val maps, "
            f"device {device_name(device)}, class weights {[round(w, 2) for w in weights]}"
        )

        end_epoch = t["epochs"]
        if max_epochs is not None:
            end_epoch = min(end_epoch, start_epoch + max_epochs)
        for epoch in range(start_epoch, end_epoch):
            started = time.time()
            frozen = epoch < t.get("freeze_encoder_epochs", 0)
            set_encoder_frozen(model, frozen)
            train_mode(model, frozen)
            train_set.set_epoch(epoch)
            losses = []
            rates = learning_rates(epoch, t)
            for step, (images, masks) in enumerate(loader):
                rates = learning_rates(epoch + step / len(loader), t)
                set_learning_rates(optimizer, rates)
                losses.append(
                    train_step(
                        model,
                        images,
                        masks,
                        loss_fn,
                        optimizer,
                        device,
                        amp_dtype,
                        scaler,
                        t["grad_clip"],
                        channels_last,
                    )
                )

            results, preds = validate(model, val_maps, loss_fn, device, v, channels_last)
            selected = mean_scores([r for r in results if r["dataset"] in select_on])
            key = selection_key(selected)
            improved = best is None or key > best
            if improved:
                best, best_epoch, since_best = key, epoch + 1, 0
                torch.save(
                    {"model": model.state_dict(), "config": cfg, "epoch": epoch + 1, "score": key},
                    best_path,
                )
            else:
                since_best += 1

            # Logs: metrics.csv, MLflow, prediction images
            metrics = {
                "train_loss": float(np.mean(losses)),
                "lr_decoder": rates[0],
                "lr_encoder": rates[1],
                "epoch_seconds": time.time() - started,
                **{f"select/{k}": val for k, val in selected.items()},
                **{f"crop_share/{k}": val for k, val in train_set.crop_shares().items()},
            }
            for group in summarize(results):
                name = group["dataset"]
                metrics.update(
                    {f"val_{name}/{k}": val for k, val in group.items() if isinstance(val, float)}
                )
            append_metrics_csv(run_dir / "metrics.csv", {"epoch": epoch + 1, **metrics})
            mlflow.log_metrics(finite(metrics), step=epoch + 1)
            pred_dir = run_dir / "predictions" / f"epoch_{epoch + 1:02d}"
            pred_dir.mkdir(parents=True, exist_ok=True)
            for row, image, true in val_maps:
                if row["map"] in showcase:
                    showcase_image(image, true, preds[row["map"]]).save(
                        pred_dir / f"{row['map']}.jpg", quality=90
                    )
            mlflow.log_artifacts(str(pred_dir), f"predictions/{pred_dir.name}")

            torch.save(
                {
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "scaler": scaler.state_dict() if scaler is not None else None,
                    "config": cfg,
                    "epoch": epoch + 1,
                    "best": best,
                    "best_epoch": best_epoch,
                    "since_best": since_best,
                    "mlflow_run_id": active.info.run_id,
                    "python_rng": random.getstate(),
                    "numpy_rng": np.random.get_state(),
                    "torch_rng": torch.get_rng_state(),
                },
                last_path,
            )
            print(
                f"epoch {epoch + 1:2d}/{t['epochs']}  train loss {metrics['train_loss']:.4f}  "
                f"val loss {selected.get('loss', math.nan):.4f}  "
                f"wall IoU {selected.get('iou_wall', math.nan):.3f}  "
                f"wall BF1 {key[0]:.3f}  portal IoU {key[1]:.3f}"
                f"{'  *best*' if improved else ''}  ({metrics['epoch_seconds']:.0f} s)"
            )
            if since_best >= t["early_stop_patience"]:
                print(f"early stop: no better epoch for {since_best} epochs")
                break

        mlflow.log_metric("best_epoch", best_epoch)
        for path in (best_path, last_path, run_dir / "metrics.csv"):
            if path.exists():
                mlflow.log_artifact(str(path))
    print(f"best epoch {best_epoch} -> {best_path}")
    return run_dir


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--runs", type=Path, default=ROOT / "runs", help="runs folder (Drive on Colab)")
    ap.add_argument("--processed", type=Path, help="default: the manifest's folder")
    ap.add_argument("--resume", action="store_true", help="continue from <run>/last.pt")
    ap.add_argument("--max-epochs", type=int, help="stop after this many epochs (for checks)")
    args = ap.parse_args(argv)
    run(
        load_config(args.config),
        args.runs,
        args.processed,
        args.resume,
        args.config,
        args.max_epochs,
    )


if __name__ == "__main__":
    main()
