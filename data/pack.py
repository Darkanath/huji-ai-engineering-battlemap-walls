"""Zip the training data for Google Colab (docs/training.md §8).

The pack holds `manifest.csv` and the 32 px per square training copies (image and mask) of
every map in the train and val splits. Test maps never leave the laptop, and neither does the
demo fixture. Paths inside the zip are relative to data/processed/, so unzipping it gives a
folder that `train.train` can use as its processed-data folder as it is.

The file is named by a hash of `manifest.csv` (runs/packs/data-<hash>.zip), so a pack always
says which manifest it came from, and the same manifest gives the same name.

Usage:
  python -m data.pack [--processed data/processed] [--out runs/packs]
"""

import argparse
import hashlib
import zipfile
from pathlib import Path

from data.manifest import read_manifest

ROOT = Path(__file__).parents[1]
PACKED_SPLITS = ("train", "val")


def manifest_hash(manifest: Path) -> str:
    """The first 10 hex digits of the SHA-256 of the manifest file."""
    return hashlib.sha256(manifest.read_bytes()).hexdigest()[:10]


def pack_files(processed: Path) -> list[str]:
    """Paths (relative to `processed`) of the 32 px image and mask of every train/val map."""
    files = []
    for row in read_manifest(processed / "manifest.csv"):
        if row["split"] in PACKED_SPLITS:
            files += [row["image_32"], row["mask_32"]]
    return files


def build_pack(processed: Path, out_dir: Path) -> Path:
    """Write the pack zip and return its path. JPEG and PNG are already compressed, so the
    files are stored, not deflated."""
    manifest = processed / "manifest.csv"
    if not manifest.exists():
        raise FileNotFoundError(f"{manifest} not found; run python -m data.manifest first")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"data-{manifest_hash(manifest)}.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.write(manifest, "manifest.csv")
        for name in pack_files(processed):
            zf.write(processed / name, name)
    return path


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--out", type=Path, default=ROOT / "runs" / "packs")
    args = ap.parse_args(argv)

    path = build_pack(args.processed, args.out)
    n_maps = len(pack_files(args.processed)) // 2
    print(f"{n_maps} train/val maps -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print("Upload it to MyDrive/battlemap-walls/packs/ for notebooks/colab_train.ipynb.")


if __name__ == "__main__":
    main()
