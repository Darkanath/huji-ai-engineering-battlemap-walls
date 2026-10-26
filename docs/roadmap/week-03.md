# Week 3 · 3–9.11 · First U-Net on synthetic data

**Goal:** a U-Net (pretrained ResNet-18 encoder) trained on synthetic maps on a Google Colab GPU,
logged to MLflow, and scored on the validation split against the Canny baseline. All training settings follow
[training.md](../training.md).

## You

- [ ] 5 more Dungeondraft layouts × 4 variants: `dd09`–`dd13`, as specified in
      [map-specs.md](../map-specs.md).
- [ ] Start the hand-labeled test set (10–15 maps in total by week 6): collect the images in
      `data/raw/test/`, list them in `data/raw/test/test_maps.csv`, and trace them in Dungeondraft
      following "Hand-tracing the test set" in the labeling rules (export, then
      `data/attach_image.py` swaps the original image in). Third-party maps never leave
      `data/raw/test/`.
- [ ] Upload the data pack to `MyDrive/battlemap-walls/packs/` and run
      `notebooks/colab_train.ipynb` for the benchmark, the checks (training.md §10) and the stage 1
      run. Copy `runs/<run>/` back from Drive.

## Code

| File | What |
| --- | --- |
| `train/dataset.py` | Reads the manifest; loads the 32 px training copies; samples 2,000 biased 256×256 crops per epoch (45% on walls, 20% on portals, 10% on lights, 25% anywhere; see training.md §2). |
| `train/augment.py` | Flips, 90° rotations, color jitter, hue shift, blur, JPEG noise. Geometric changes go to image and mask together; color changes go to the image only. |
| `train/model.py` | `smp.Unet("resnet18", classes=4)`; device = CUDA if available, else XPU if `torch.xpu.is_available()`, else CPU (one function, `.to(device)`); on CPU `torch.set_num_threads(6)` and channels-last; mixed precision on CUDA (training.md §8). |
| `train/losses.py` | Cross-entropy + Dice (Dice over wall, portal and light), class weights computed from the training split's pixel shares in the manifest. |
| `train/train.py` | Seeded training loop: frozen encoder for the first epochs, then unfreeze; validation each epoch (loss, wall, portal and light IoU, boundary F1); best checkpoint by validation boundary F1 to `runs/<run>/`; `last.pt` every epoch and `--resume` to continue after a Colab disconnect; `--runs` sets the runs folder (Drive on Colab); everything logged to MLflow with the config, device and GPU name. Saves sample predictions at early, middle and final epochs. |
| `train/configs/stage1_synthetic.toml` | Stage 1 settings: data, epochs, learning rates, freeze schedule, seed. |
| `data/pack.py` | Zip `manifest.csv` and the 32 px train and val copies (not test) into `runs/packs/data-<manifest hash>.zip` for Colab. |
| `notebooks/colab_train.ipynb` | Mount Drive, clone the repo at a commit, install the project on Colab's CUDA PyTorch, unzip the pack to local disk, run `train.train` with runs on Drive, resume if `last.pt` exists. |
| `data/attach_image.py` | Replace a .dd2vtt's embedded image with the original test image; set `pixels_per_grid` = image width / `map_size.x`; refuse images that aren't `map_size` × a whole px per square. For the hand-traced test set. |
| `tests/test_dataset.py` | Crops are 256×256, masks hold only 0–3, rescaling keeps walls and lights in place. |
| `tests/test_train_smoke.py` | Two training steps on the demo map run on CPU without error and lower the loss; a run stopped after one epoch resumes from `last.pt` to the same result. |
| `tests/test_pack.py` | The pack holds the manifest and the train/val 32 px copies, and no test-split files. |
| `tests/test_attach_image.py` | Size check rejects a wrong-sized image; output loads with `load_uvtt`. |

First: generate the full synthetic set (`python -m data.generator --count 500`) and rebuild the
manifest. Also add `data/contact_sheet.py`, a thumbnail grid per dataset for the presentation.

Then the EDA notebook, `notebooks/eda.ipynb` (course requirement; contents in PLAN.md, "Data
cleaning & EDA"), and start `docs/lessons.md`: one dated line per thing that didn't work or
changed the plan, for the presentation.

## Run

```bash
docker compose run --rm app python -m data.generator --count 500
docker compose run --rm app python -m data.manifest
docker compose run --rm app python -m data.pack            # then upload the zip to Drive
# On Colab: notebooks/colab_train.ipynb with train/configs/stage1_synthetic.toml
# Back on the laptop, after copying runs/<run>/ from Drive:
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

- `segmentation_models_pytorch`, `albumentations`, `mlflow` (in CLAUDE.md), in the Docker image
  and installed by the Colab notebook. Colab's own CUDA PyTorch is used there, never added to
  the image.
- The pretrained encoder weights download once; they are cached in a volume (`TORCH_HOME` under `runs/`) so later runs work offline.
