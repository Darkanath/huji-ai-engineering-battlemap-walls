# Training plan

How every model in this project is trained, validated and selected. The week-by-week tasks are in
[roadmap/](roadmap/README.md) (weeks 3–6). The reasons behind the overall approach are in
[PLAN.md](PLAN.md). Numbers marked *(estimate)* get measured in week 3 and updated here.

## 1. Models

| Run | Model | Trained on | Starts from | Purpose |
| --- | --- | --- | --- | --- |
| R0 | Canny + contours | nothing (thresholds tuned) | - | Classical baseline |
| R1 | U-Net, ResNet-18 encoder | synthetic train | ImageNet encoder | Stage 1; also the "synthetic only" ablation |
| R2 | U-Net, ResNet-18 encoder | real train (Dungeondraft + Dungeon Alchemist) | R1 best checkpoint | Stage 2: **main model** ("synthetic -> real") |
| R3 | U-Net, ResNet-18 encoder | real train | ImageNet encoder | "Real only" ablation |
| R4 | U-Net, ResNet-18 encoder | as R1 + R2, at native 70 px per square | as R1 | "No scale normalization" ablation |
| R5 *(stretch)* | U-Net, MobileNetV3 encoder | as R1 + R2 | ImageNet encoder | Accuracy vs CPU speed |

That makes 5–6 trained runs in total. The list is fixed now; nothing gets added later.

**Network:** `smp.Unet(encoder_name="resnet18", encoder_weights="imagenet", in_channels=3,
classes=4)`, about 14 M parameters. It outputs logits for 0 background, 1 wall, 2 portal,
3 light. Every run, from R1 on, uses all 4 classes: adding lights later would mean retraining
every run. Lights do not change checkpoint selection (§6).
Inputs are RGB normalized with ImageNet mean and std, to match the pretrained encoder.

## 2. Data

### Sources and splits

| Dataset | Maps | Split | Used for |
| --- | --- | --- | --- |
| Synthetic | 500 (more only if R1 shows it helps) | 90% train / 10% val, by map | R1, R4 stage 1 |
| Dungeondraft | 13 layouts × 4 variants | ~70 / 15 / 15 by **layout** | R2, R3, R4 stage 2; validation for all runs |
| Dungeon Alchemist | 6 layouts × 4 variants | ~70 / 15 / 15 by **layout** (at least 1 layout each in val and test) | as Dungeondraft |
| Test | 10–15 hand-traced maps (in-domain and hard), plus the real test layouts | test only | Final evaluation, **once**, week 8 |

**Real** means Dungeondraft and Dungeon Alchemist together: both are maps made for the project,
labeled from their own export. They are split separately (so each tool is in every split), then
pooled for training, validation and selection. Results are also logged per tool, to show whether
the model does better on one art style.

- `data/manifest.py` assigns splits per dataset with a fixed seed and writes them to
  `data/processed/manifest.csv`. All variants of a layout stay in one split. Splits never change
  after they are first written.
- The demo map (`demo-training-map`) is a test fixture only and is not used in any split.

### Training copies at 32 px per square

The manifest step also writes a training copy of every map into
`data/processed/<dataset>/32px/`, so nothing is generated during training:

- **Image:** the embedded image resized to 32 px per square (area interpolation), saved as JPEG
  (quality 95). A 25×25 map becomes 800×800 px.
- **Mask:** rasterized **directly** from the .dd2vtt at 32 px per square, not resized from the
  70 px mask, so thin portals keep their exact shape. Walls are 8 px wide and portals 10 px;
  light discs have a radius of 8, 13 or 19 px (small, medium, large tier).

R4 (no scale normalization) uses the 70 px copies instead.

### Crop sampling

- Each epoch draws **2,000 random 256×256 crops** (8×8 squares) from the training maps. Every
  map gets the same number of crops, whatever its size.
- **Biased crops:** 45% are centered on a random wall pixel, 20% on a random portal pixel, 10% on
  a random light pixel, 25% anywhere. Without this, portals (under 1% of pixels) and lights (about
  0.1–0.3% *(estimate)*) would be missing from most crops. A map with no lights gives its light
  share to the random crops.
- The sampling is seeded with `seed + epoch`, so a run can be repeated exactly.
- The class shares of the sampled crops are logged every epoch, to check the bias.

## 3. Augmentation

Applied to training crops only, with `albumentations`. Geometric transforms move the image and
the mask together; the mask always uses nearest-neighbor interpolation. Color transforms change
the image only.

| Transform | Setting | p |
| --- | --- | --- |
| Horizontal flip, vertical flip | - | 0.5 each |
| 90° rotation | k ∈ {1, 2, 3} | 0.5 |
| Scale jitter | ±10%, then crop back to 256 | 0.3 |
| Brightness and contrast | ±0.2 | 0.5 |
| Hue, saturation, value | ±10, ±20, ±10 | 0.5 |
| Gamma | 80–120 | 0.2 |
| Grayscale | - | 0.05 |
| Gaussian blur | kernel 3–5 | 0.2 |
| Gaussian noise | small | 0.2 |
| JPEG compression | quality 50–95 | 0.3 |

- Scale jitter stays small (±10%), because scale normalization is what keeps walls about 8 px
  thick. It covers small errors in grid detection or in the user-entered map width.
- No elastic or perspective transforms: they bend straight walls, and maps are always top-down.
- Before the first long run, save a contact sheet of 32 augmented crops with their masks overlaid
  and check it by eye.

## 4. Loss

`loss = CE_weighted + Dice` (equal weights).

- **Weighted cross-entropy:** class weight `w_c = 1 / sqrt(share_c)`, normalized so background is
  1 and capped at 20. Shares come from the **training split of the current stage** in the
  manifest (not from the biased crops). With today's Dungeondraft shares (about 94% / 5.3% /
  0.5%) this gives roughly 1 / 4.2 / 13.7; lights at about 0.2% *(estimate)* hit the cap of 20.
- **Dice:** soft multi-class Dice on the softmax, averaged over wall, portal and light. Background
  is left out, because its Dice is always near 1 and adds nothing.
- If portal or light IoU stays low after stage 2, the one planned change is focal loss in place
  of weighted CE. Any change gets its own MLflow run, so it shows up in the report.

## 5. Optimization

| Setting | Stage 1 (R1, R3, R4) | Stage 2 (R2, R4) |
| --- | --- | --- |
| Optimizer | AdamW, weight decay 1e-4 | AdamW, weight decay 1e-4 |
| Batch size | 8 | 8 |
| Epochs | 30 (max) | 20 (max) |
| Encoder frozen | epochs 1–5 | never |
| Learning rate, decoder | 1e-3 | 1e-4 |
| Learning rate, encoder (after unfreezing) | 1e-4 | 1e-5 |
| Schedule | 1-epoch linear warmup after unfreezing, then cosine decay to 1e-6 | cosine decay to 1e-7 |
| Early stopping | 8 epochs without a better checkpoint | 6 epochs |
| Gradient clipping | norm 1.0 | norm 1.0 |

- **Freezing:** while the encoder is frozen, its BatchNorm layers stay in eval mode, so their
  ImageNet statistics are not overwritten by small CPU batches.
- **Stage 2** loads R1's best checkpoint, including the decoder, and reuses the same augmentation.
  Only the data, learning rates and epoch count change.

## 6. Validation and checkpoint selection

Run at the end of every epoch, on **whole maps**, not crops:

- **Inference:** sliding 256×256 windows with stride 192 (the last window moved in to end at
  the map edge); softmax probabilities averaged where
  windows overlap; class = argmax. This is the same code (`train/predict.py`) the app uses.
- **Validation sets:** real val (Dungeondraft + Dungeon Alchemist) for every run (the target
  domain), plus synthetic val in stage 1. All are logged, real val also per tool; **selection uses
  real val only.**
- **Metrics each epoch:** validation loss; pixel IoU and F1 for wall, portal and light; wall
  boundary F1 with a tolerance of 3 px (0.1 square at 32 px per square).
- **Light F1 and tier accuracy** need the light post-processing (`postprocess/lights.py`, week 6),
  so they run on the selected checkpoint of each run, like visibility IoU.
- **Visibility IoU** is slower, so it runs only on the selected checkpoint (from week 5).
- **Checkpoint selection:** the best epoch by **real val wall boundary F1**. Ties go to the
  higher portal IoU. `best.pt` and `last.pt` are both kept.
- **Final model:** the run with the best real val boundary F1 across R1–R5, chosen in week
  6. Only then does the test set run, once.

## 7. Canny baseline (R0)

- Pipeline: grayscale -> Gaussian blur -> Canny -> morphological close -> keep contours longer
  than a minimum length -> draw them as 8 px walls. It predicts no portals and no lights (portal
  and light IoU are 0).
- Tuning: a grid search over blur kernel, the two Canny thresholds, the close kernel and the
  minimum length, on **real val**, maximizing wall boundary F1 (`python -m eval.baseline_canny`).
  The best values go into `eval/configs/baseline_canny.toml`, with a note of the maps they were
  tuned on.
- **First tuning (21.10):** on `dd03_a`–`dd03_d`, the only real val layout so far, a map with no
  furniture, so the score is optimistic. Best: blur 7, Canny 20/40, close 5, min length 6
  squares; val wall boundary F1 0.845 (IoU 0.384). The grid was widened twice until no winning
  value sat on its edge.
- **Retuned once, in week 4**, when the real set is complete (`--retune`), so the baseline is
  tuned on the same val set the U-Net is selected on. After that the config is frozen.

## 8. Compute: Colab for training, the laptop for everything else

**Decided (21.10):** every training run (R1–R5) runs on a Google Colab GPU. Data, evaluation,
inference and the app stay on the laptop, under Docker, on the CPU.

**The round trip:**

1. **Laptop:** build the data (`data.generator`, `data.manifest`), then
   `python -m data.pack` zips `manifest.csv` and the 32 px training copies of the train and val
   splits (the test split never leaves the laptop) into `runs/packs/data-<hash>.zip`, named by a
   hash of `manifest.csv`. Upload it to `MyDrive/battlemap-walls/packs/`.
2. **Colab** (`notebooks/colab_train.ipynb`): mount Drive, clone the repo at the commit to train
   (a GitHub token from Colab secrets if the repo is private), install the project without
   PyTorch (Colab's CUDA build is already there), unzip the pack to local disk, and run
   `python -m train.train --config ... --runs /content/drive/MyDrive/battlemap-walls/runs`.
   Checkpoints, `metrics.csv` and MLflow logs go straight to Drive, so a disconnect loses at most
   one epoch.
3. **Resume:** `--resume` continues from `runs/<run>/last.pt` (model, optimizer, scheduler, epoch,
   best score and RNG states, saved every epoch).
4. **Laptop:** copy `runs/<run>/` from Drive into `runs/`, then evaluate, export to ONNX and use
   the model locally on the CPU.

**Settings:**

- **Device** (`train/model.py`, one function): CUDA if available, else XPU, else CPU; always
  `.to(device)`. The run logs the device and GPU name.
- **Precision:** on CUDA, mixed precision (`torch.autocast`): bfloat16 if the GPU supports it,
  else float16 with a gradient scaler. On the CPU, float32.
- **Data loading:** on Colab, 2–4 DataLoader workers reading from local disk (not Drive, which is
  slow for many small files). On the CPU fallback, `torch.set_num_threads(6)` (physical cores of
  the i7-1365U), 2 workers, channels-last.
- **Determinism:** seeds as in §9, plus `torch.backends.cudnn.deterministic = True` and
  `benchmark = False`. A GPU run and a CPU run with the same seed are close but not identical;
  the report says which hardware trained each run.
- **Measured 26.10 on Colab (GPU), 500 synthetic + real maps:** 50 steps 21.5 s, validation of
  54 maps 16.1 s, so about **2.1 min per epoch and 1.0 h for 30 epochs**: a whole run fits one
  session. About 0.4 s per step is slow for a GPU, so data loading (2 vCPUs doing augmentation)
  is likely the limit, not the GPU; fine at this run length. Overfit test passed (loss 3.25 ->
  0.006 in 200 steps).
- **Benchmark first (week 3):** time 50 training steps and one validation pass on Colab. With a
  GPU the epoch counts in §5 stay as they are; the run list in §1 stays fixed too. The time saved
  goes into the checks in §10 and into retries, not into more runs.
- **Time per run** *(CPU fallback; measured 26.10 on 18 synthetic maps: about 0.15–0.2 s per
  crop plus about 6 s to validate 6 maps)*: 5–8 minutes per 2,000-crop epoch; stage 1 at 30 epochs ≈ 5 hours, stage 2 at 20 epochs ≈ 3.5 hours. On a Colab
  GPU, expect minutes per epoch; measured in week 3.

## 9. Reproducibility and logging

- **Seeds:** one `seed` per run in the config. It seeds `random`, `numpy` and `torch`, DataLoader
  workers (`worker_init_fn`) and crop sampling (`seed + epoch`).
- **MLflow** (tracking store in `runs/mlruns`, plain files; MLflow 3 needs
  `MLFLOW_ALLOW_FILE_STORE=true` for that, which `train/train.py` sets, because an SQLite store is
  unreliable on Google Drive), for every run:
  - params: the whole TOML config, the git commit, a hash of `manifest.csv`, device and GPU
    name, precision;
  - metrics per epoch: training loss, validation loss, IoU, F1, boundary F1, crop class shares,
    learning rates, epoch time;
  - artifacts: the config file, `best.pt`, `last.pt`, and prediction images for 6 fixed
    real val maps (at least 2 from each tool) at epoch 1, the middle epoch and the final epoch.
- **Run folder:** `runs/<run-name>/` with the checkpoints, the config copy, `metrics.csv` and the
  prediction images, so everything the report needs is in the folder itself, whatever machine
  MLflow ran on.

## 10. Checks before a full run

1. `pytest` passes, including the 2-step training smoke test.
2. **Overfit test:** one batch of 8 crops for 200 steps; the loss must go close to 0. If it
   doesn't, there is a bug in the data, the loss or the model.
3. The augmented-crop contact sheet looks right: masks line up with walls after every transform.
4. Crop class shares are near the planned bias (walls and portals present in most crops).
5. The benchmark time per epoch is measured and the run fits one Colab session, or resumes cleanly.

## 11. Config

One TOML file per run in `train/configs/`, read with Python's built-in `tomllib`. For example,
`train/configs/stage1_synthetic.toml`:

```toml
run_name = "r1_stage1_synthetic"
seed = 42

[data]
manifest = "data/processed/manifest.csv"
train = ["synthetic"]
val = ["dungeondraft", "dungeon_alchemist", "synthetic"]
select_on = ["dungeondraft", "dungeon_alchemist"]   # pooled: the real val set
px_per_square = 32
crop_size = 256
crops_per_epoch = 2000
crop_bias = { wall = 0.45, portal = 0.2, light = 0.1, random = 0.25 }

[model]
arch = "unet"
encoder = "resnet18"
encoder_weights = "imagenet"
init_checkpoint = ""          # stage 2: "runs/r1_stage1_synthetic/best.pt"

[train]
epochs = 30
batch_size = 8
freeze_encoder_epochs = 5
lr_decoder = 1e-3
lr_encoder = 1e-4
weight_decay = 1e-4
warmup_epochs = 1
min_lr = 1e-6
early_stop_patience = 8
grad_clip = 1.0

[loss]
ce_weight = 1.0
dice_weight = 1.0
class_weight_cap = 20.0

[val]
window = 256
stride = 192
boundary_tolerance_px = 3

[runtime]
device = "auto"               # cuda, then xpu, then cpu
precision = "auto"            # cuda: bf16 if supported, else fp16 + grad scaler; cpu: fp32
workers = 2
threads = 6                   # cpu only
channels_last = true
```

## 12. Files

| File | Role |
| --- | --- |
| `data/manifest.py` | Splits, manifest, 32 px training copies |
| `train/dataset.py` | Biased crop sampling from the 32 px copies |
| `train/augment.py` | The augmentation table above |
| `data/pack.py` | Zip the manifest and 32 px train/val copies for Colab |
| `notebooks/colab_train.ipynb` | Run `train.train` on a Colab GPU, data and runs on Drive |
| `train/model.py` | Model construction, freezing, device (CUDA, XPU, CPU) and thread setup |
| `train/losses.py` | Weighted CE + Dice, class weights from the manifest |
| `train/train.py` | Training loop, validation, resumable checkpoints, MLflow |
| `train/predict.py` | Sliding-window inference (validation and the app) |
| `eval/metrics.py` | IoU, F1, boundary F1, light F1 and tier accuracy |
| `eval/baseline_canny.py` | R0 |
| `train/configs/*.toml` | One config per run |

## 13. What goes into the report

- **Data summary:** maps, crops and class shares per split, from the manifest, plus light counts
  per tier.
- **Training curves:** training and validation loss and validation wall IoU per epoch for stage 1
  and stage 2, with the chosen checkpoint marked.
- **Learning progression:** the 6 fixed validation maps at the first, middle and final epoch.
- **Results table:** R0–R5 on validation (week 6), then on both test sets (week 8).
