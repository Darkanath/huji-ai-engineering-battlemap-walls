"""The segmentation model, its input preprocessing, encoder freezing and the runtime device.

The model is a U-Net with a pretrained encoder (`segmentation_models_pytorch`), 4 output
classes (docs/training.md §1). Inputs are RGB normalized with the ImageNet mean and std, to
match the pretrained encoder; `preprocess` is the one place that does it, for training,
validation and the app alike.

Device choice lives here and only here (CLAUDE.md): CUDA if available (Colab), else Intel XPU
if `torch.xpu.is_available()`, else CPU. Code always moves tensors with `.to(device)`.
"""

import os

import numpy as np
import segmentation_models_pytorch as smp
import torch
from torch import nn

from data.rasterize import CLASS_NAMES

NUM_CLASSES = len(CLASS_NAMES)  # 0 background, 1 wall, 2 portal, 3 light
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def build_model(
    arch: str = "unet", encoder: str = "resnet18", encoder_weights: str | None = "imagenet"
) -> nn.Module:
    """A U-Net with `encoder`; `encoder_weights` "imagenet" or None/"" for random weights."""
    if arch != "unet":
        raise ValueError(f"unknown arch {arch!r}; only 'unet' is supported")
    return smp.Unet(
        encoder_name=encoder,
        encoder_weights=encoder_weights or None,
        in_channels=3,
        classes=NUM_CLASSES,
    )


def preprocess(image: np.ndarray) -> torch.Tensor:
    """uint8 RGB image (H, W, 3) -> normalized float tensor (3, H, W)."""
    x = (image.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    return torch.from_numpy(x.transpose(2, 0, 1).copy())


def set_encoder_frozen(model: nn.Module, frozen: bool) -> None:
    """Freeze or unfreeze the encoder's weights (only the decoder trains while frozen)."""
    for param in model.encoder.parameters():
        param.requires_grad = not frozen


def train_mode(model: nn.Module, encoder_frozen: bool) -> None:
    """Put the model in training mode; a frozen encoder stays in eval mode, so its BatchNorm
    keeps the ImageNet statistics instead of learning them from small batches."""
    model.train()
    if encoder_frozen:
        model.encoder.eval()


def pick_device(preference: str = "auto") -> torch.device:
    """The device to run on: `preference` if not "auto", else CUDA, then XPU, then CPU."""
    if preference != "auto":
        return torch.device(preference)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return torch.device("xpu")
    return torch.device("cpu")


def device_name(device: torch.device) -> str:
    """A readable name of the hardware, for the run log (GPU name on CUDA)."""
    if device.type == "cuda":
        return torch.cuda.get_device_name(device)
    if device.type == "xpu":
        return torch.xpu.get_device_name(device)
    return f"cpu ({os.cpu_count()} logical cores)"


def setup_cpu(threads: int) -> None:
    """On the CPU, use `threads` threads (the physical core count, CLAUDE.md)."""
    if threads > 0:
        torch.set_num_threads(threads)


def autocast_dtype(device: torch.device, precision: str = "auto") -> torch.dtype | None:
    """The mixed-precision dtype for `device`: on CUDA bfloat16 if supported, else float16;
    elsewhere None (float32). `precision` "fp32" turns mixed precision off everywhere."""
    if precision == "fp32" or device.type != "cuda":
        return None
    if precision == "bf16" or (precision == "auto" and torch.cuda.is_bf16_supported()):
        return torch.bfloat16
    return torch.float16
