"""
speech/text_to_speech/ultron_dsp.py – Avengers: Age of Ultron Voice DSP Filter
=============================================================================
Recreates the iconic James Spader Ultron vocal processing:
1. Deep baritone pitch/formant downward shift (-3 semitones)
2. Theatrical, deliberate pacing (length scaling)
3. Heavy mechanical chassis resonance (140Hz low-shelf boost)
4. Vibranium metallic comb filtering (hollow robotic chamber reflection)
5. Subtle 55Hz sub-harmonic ring modulation (electronic core hum)
6. Warm analog tape soft-saturation (tanh) and peak-safe normalization
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
from scipy import signal

@dataclass
class UltronAudioChunk:
    audio_float_array: np.ndarray
    sample_rate: int
    sample_channels: int = 1


def apply_ultron_voice_effect(
    audio: np.ndarray,
    sample_rate: int = 22050,
    pitch_factor: float = 0.865,
    comb_feedback: float = 0.38,
    comb_delay_ms: float = 7.5,
    bass_boost_gain: float = 0.45,
    ring_mod_gain: float = 0.12,
    saturation_drive: float = 1.35,
) -> np.ndarray:
    """
    Transform a raw voice audio signal into the unmistakable Ultron voice from Marvel's
    Avengers: Age of Ultron.
    """
    if len(audio) == 0:
        return audio

    x = audio.astype(np.float32)

    # 1. Pitch Shift Down into deep menacing baritone (~ -2.5 to -3 semitones)
    target_length = max(1, int(len(x) / pitch_factor))
    x_pitched = signal.resample(x, target_length)

    # Elongate cadence slightly for James Spader's deliberate theatrical delivery
    new_len = int(len(x) * 1.08)
    indices = np.linspace(0, len(x_pitched) - 1, new_len)
    x_pitched = np.interp(indices, np.arange(len(x_pitched)), x_pitched).astype(np.float32)

    # 2. Low-frequency Bass Chassis Resonance (boost around 140-160Hz)
    nyquist = sample_rate / 2.0
    cutoff = min(160.0 / nyquist, 0.95)
    sos_bass = signal.iirfilter(2, cutoff, btype='lowpass', output='sos')
    bass_component = signal.sosfilt(sos_bass, x_pitched) * bass_boost_gain

    # 3. Metallic Comb Filter (Vibranium chassis acoustic resonance)
    # Implemented via high-speed vectorized IIR filter: H(z) = 1 / (1 - a * z^-D)
    delay_samples = max(1, int((comb_delay_ms / 1000.0) * sample_rate))
    b = np.zeros(1, dtype=np.float32)
    b[0] = 1.0
    a = np.zeros(delay_samples + 1, dtype=np.float32)
    a[0] = 1.0
    a[-1] = -comb_feedback
    comb = signal.lfilter(b, a, x_pitched).astype(np.float32)

    # 4. Subtle Sub-harmonic Ring Modulator (55Hz core hum)
    t = np.arange(len(x_pitched), dtype=np.float32) / sample_rate
    sub_carrier = np.sin(2 * np.pi * 55.0 * t).astype(np.float32)
    ring_mod = x_pitched * sub_carrier * ring_mod_gain

    # 5. Composite Mix: dry body + metallic reflection + sub-bass + core hum
    mixed = (x_pitched * 0.55) + (comb * 0.35) + bass_component + ring_mod

    # 6. Warm Analog Tape Saturation (non-linear soft clipping via tanh)
    saturated = np.tanh(mixed * saturation_drive)

    # Peak normalization to prevent digital distortion
    peak = np.max(np.abs(saturated))
    if peak > 1e-4:
        saturated = saturated * (0.92 / peak)

    return saturated.astype(np.float32)
