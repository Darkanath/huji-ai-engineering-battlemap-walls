# Week 3 · 3–9.11 · First U-Net on synthetic data

**Goal:** a U-Net (pretrained ResNet-18 encoder) trained on synthetic maps, logged to MLflow, and
scored on the validation split against the Canny baseline. All training settings follow
[training.md](../training.md).

## You

- [ ] 5 more Dungeondraft layouts × 4 variants: `dd09`–`dd13`.
- [ ] Start the hand-labeled test set (10–15 maps in total by week 6): collect the images in
      `data/raw/test/`, trace them following "Hand-tracing the test set" in the labeling rules.
      One way: trace over the image in Dungeondraft, export .dd2vtt, then replace its embedded
      image with the original (`data/attach_image.py`, below). Third-party maps never leave
      `data/raw/test/`.
- [ ] Start the overnight training run.

## Code

| File | What |
| --- | --- |
| `train/dataset.py` | Reads the manifest; loads the 32 px training copies; samples 2,000 biased 256×256 crops per epoch (50% on walls, 25% on portals, 25% anywhere; see training.md §2). |
| `train/augment.py` | Flips, 90° rotations, color jitter, hue shift, blur, JPEG noise. Geometric changes go to image and mask together; color changes go to the image only. |
| `train/model.py` | `smp.Unet("resnet18", classes=3)`, channels-last; device = XPU if `torch.xpu.is_available()`, else CPU; `torch.set_num_threads(6)`. |
| `train/losses.py` | Cross-entropy + Dice, class weights computed from the training split's pixel shares in the manifest. |
| `train/train.py` | Seeded training loop: frozen encoder for the first epochs, then unfreeze; validation each epoch (loss, wall IoU, boundary F1); best checkpoint by validation boundary F1 to `runs/<run>/`; everything logged to MLflow with the config. Saves sample predictions at early, middle and final epochs. |
| `train/configs/stage1_synthetic.toml` | Stage 1 settings: data, epochs, learning rates, freeze schedule, seed. |
| `data/attach_image.py` | Replace a .dd2vtt's embedded image with a given image file, checking the size matches `map_size` × `pixels_per_grid`. For the hand-traced test set. |
| `tests/test_dataset.py` | Crops are 256×256, masks hold only 0–2, rescaling keeps walls in place. |
| `tests/test_train_smoke.py` | Two training steps on the demo map run without error and lower the loss. |
| `tests/test_attach_image.py` | Size check rejects a wrong-sized image; output loads with `load_uvtt`. |

First: generate the full synthetic set (`python -m data.generator --count 500`) and rebuild the
manifest. Also add `data/contact_sheet.py`, a thumbnail grid per dataset for the presentation.

## Run

```bash
docker compose run --rm app python -m data.generator --count 500
docker compose run --rm app python -m data.manifest
docker compose run --rm app python -m train.train --config train/configs/stage1_synthetic.toml
docker compose run --rm -p 5000:5000 app mlflow ui --host 0.0.0.0 --backend-store-uri runs/mlruns
```

## Done when

- [ ] 500 synthetic maps on disk, in the manifest, with a contact sheet.
- [ ] Stage 1 run finished; best checkpoint saved; curves visible in MLflow.
- [ ] U-Net beats Canny on synthetic validation wall IoU and boundary F1.
- [ ] All tests pass.

## Report

- Training curves for stage 1 (loss, validation wall IoU).
- Learning progression images (early, middle, final epoch) for 4–6 validation maps.

## Dependencies

- `segmentation_models_pytorch`, `albumentations`, `mlflow` (in CLAUDE.md).
- The pretrained encoder weights download once; they are cached in a volume (`TORCH_HOME` under `runs/`) so later runs work offline.
