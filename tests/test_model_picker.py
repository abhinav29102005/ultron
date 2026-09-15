"""Tests for hardware-based local model selection."""

from __future__ import annotations

from utils.model_picker import LOW_DISK_GB, TIERS, choose_tier, describe


class TestTierSelection:
    def test_thin_laptop_gets_the_smallest_model(self):
        assert choose_tier(ram_gb=4, vram_gb=0, free_disk_gb=50).model == "qwen2.5:1.5b"

    def test_typical_laptop_gets_the_standard_model(self):
        # 16 GB RAM but only 4 GB VRAM: a 7B would spill to CPU and be slower.
        assert choose_tier(ram_gb=16.8, vram_gb=4, free_disk_gb=71).model == "qwen3:4b-instruct"

    def test_gaming_laptop_gets_the_performance_model(self):
        assert choose_tier(ram_gb=16, vram_gb=6, free_disk_gb=50).model == "qwen2.5:7b"

    def test_workstation_gets_the_largest_model(self):
        assert choose_tier(ram_gb=32, vram_gb=12, free_disk_gb=100).model == "qwen2.5:14b"

    def test_plenty_of_ram_but_no_gpu_stays_standard(self):
        """VRAM gates the big models on purpose."""
        assert choose_tier(ram_gb=64, vram_gb=0, free_disk_gb=200).model == "qwen3:4b-instruct"


class TestConstraints:
    def test_low_disk_forces_a_smaller_model(self):
        """A model that cannot be downloaded is no use, however fast the machine."""
        big = choose_tier(ram_gb=32, vram_gb=12, free_disk_gb=100)
        cramped = choose_tier(ram_gb=32, vram_gb=12, free_disk_gb=3)
        assert big.model == "qwen2.5:14b"
        assert cramped.model == "qwen2.5:1.5b"

    def test_disk_headroom_is_respected(self):
        """7B is ~4.7 GB; 5 GB free is not enough once headroom is counted."""
        assert choose_tier(ram_gb=16, vram_gb=6, free_disk_gb=5).model != "qwen2.5:7b"

    def test_failed_probes_degrade_to_the_smallest(self):
        """Guessing high produces an unusable install, so assume the worst."""
        assert choose_tier(ram_gb=0, vram_gb=0, free_disk_gb=0).model == "qwen2.5:1.5b"

    def test_never_returns_none(self):
        for ram in (0, 4, 8, 16, 32, 64):
            for vram in (0, 4, 8, 24):
                assert choose_tier(ram, vram, 100) is not None


class TestTierTable:
    def test_tiers_are_ordered_smallest_first(self):
        sizes = [t.approx_gb for t in TIERS]
        assert sizes == sorted(sizes)

    def test_requirements_increase_with_size(self):
        rams = [t.min_ram_gb for t in TIERS]
        assert rams == sorted(rams)

    def test_low_disk_threshold_is_sane(self):
        assert 0 < LOW_DISK_GB < TIERS[-1].approx_gb


class TestDescribe:
    def test_mentions_the_chosen_model(self):
        specs = {
            "ram_gb": 16.8, "vram_gb": 4.0, "free_disk_gb": 71.3,
            "tier": "standard", "model": "qwen2.5:3b",
            "approx_gb": 1.9, "low_disk": False,
        }
        text = describe(specs)
        assert "qwen2.5:3b" in text and "16.8" in text

    def test_says_when_there_is_no_gpu(self):
        specs = {
            "ram_gb": 8.0, "vram_gb": 0.0, "free_disk_gb": 40.0,
            "tier": "standard", "model": "qwen2.5:3b",
            "approx_gb": 1.9, "low_disk": False,
        }
        assert "no dedicated GPU" in describe(specs)
