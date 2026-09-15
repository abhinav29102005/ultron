"""
utils/model_picker.py – Choose a local model that fits the machine
==================================================================
Bootstrap used to have no opinion about which local model to install, and the
model name was hardcoded in ``config/settings.py``. A 1.5B model wastes a
workstation; a 14B model is unusable on a thin laptop.

This module probes RAM, GPU VRAM and free disk, then picks from a tier table.

VRAM is weighted deliberately. Ollama will happily run a model larger than the
GPU can hold by spilling layers to the CPU, which is *slower* than simply
running a smaller model, so a big model is only chosen when it will actually
fit on the card.

Everything degrades: if a probe fails we assume the conservative value rather
than guessing high, because guessing high produces an unusable install.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTier:
    """One rung of the ladder."""

    name: str
    model: str
    approx_gb: float
    min_ram_gb: float
    min_vram_gb: float


#: Ordered smallest to largest. The best tier whose requirements are met wins.
TIERS: tuple[ModelTier, ...] = (
    ModelTier("minimal", "qwen2.5:1.5b", 1.0, min_ram_gb=0.0, min_vram_gb=0.0),
    # The -instruct tag matters. Plain qwen3:4b is a hybrid reasoning model
    # whose thinking cannot be turned off through Ollama, and its trace eats
    # the whole token budget on open-ended prompts: measured 16-30s per chat
    # reply here, some returning nothing at all. The instruct release is the
    # same generation without that, and answers in 1.5-2.2s.
    # Anything this tier installs must match what config/settings.py defaults
    # to, or bootstrap recommends a model the app is not configured to use.
    ModelTier("standard", "qwen3:4b-instruct", 2.5, min_ram_gb=8.0, min_vram_gb=0.0),
    ModelTier("performance", "qwen2.5:7b", 4.7, min_ram_gb=16.0, min_vram_gb=6.0),
    ModelTier("max", "qwen2.5:14b", 9.0, min_ram_gb=32.0, min_vram_gb=12.0),
)

#: Below this much free disk we refuse to consider anything but the smallest.
LOW_DISK_GB = 5.0


def detect_ram_gb() -> float:
    try:
        import psutil

        return psutil.virtual_memory().total / 1e9
    except Exception:
        return 0.0


def detect_vram_gb() -> float:
    """Total VRAM of the largest NVIDIA GPU, or 0.0 when there isn't one.

    Returns 0.0 for AMD/Intel/Apple GPUs too: without a reliable cross-vendor
    probe, treating them as CPU-only picks a smaller model, which runs badly
    at worst rather than not at all.
    """
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return 0.0
        values = [float(line.strip()) for line in out.stdout.splitlines() if line.strip()]
        return max(values) / 1024.0 if values else 0.0
    except Exception:
        return 0.0


def detect_free_disk_gb(path: str = ".") -> float:
    try:
        return shutil.disk_usage(path).free / 1e9
    except Exception:
        return 0.0


def choose_tier(
    ram_gb: float,
    vram_gb: float,
    free_disk_gb: float,
) -> ModelTier:
    """Best tier the machine can actually run, never smaller than minimal."""
    best = TIERS[0]

    for tier in TIERS:
        if ram_gb >= tier.min_ram_gb and vram_gb >= tier.min_vram_gb:
            best = tier

    # Disk is a hard constraint: a model that cannot be downloaded is no use.
    # Walk back down until it fits, with headroom for the rest of the install.
    while best.approx_gb + 2.0 > free_disk_gb and best is not TIERS[0]:
        best = TIERS[TIERS.index(best) - 1]

    return best


def detect_specs() -> dict:
    """Probe the machine. Returns the raw numbers plus the chosen tier."""
    ram = detect_ram_gb()
    vram = detect_vram_gb()
    disk = detect_free_disk_gb()
    tier = choose_tier(ram, vram, disk)
    return {
        "ram_gb": round(ram, 1),
        "vram_gb": round(vram, 1),
        "free_disk_gb": round(disk, 1),
        "tier": tier.name,
        "model": tier.model,
        "approx_gb": tier.approx_gb,
        "low_disk": disk < LOW_DISK_GB,
    }


def describe(specs: dict) -> str:
    """Human-readable summary for the bootstrap prompt."""
    gpu = f"{specs['vram_gb']} GB VRAM" if specs["vram_gb"] else "no dedicated GPU detected"
    return (
        f"RAM: {specs['ram_gb']} GB | GPU: {gpu} | "
        f"Free disk: {specs['free_disk_gb']} GB\n"
        f"Selected tier '{specs['tier']}' -> {specs['model']} "
        f"(~{specs['approx_gb']} GB download)"
    )


if __name__ == "__main__":
    s = detect_specs()
    print(describe(s))
