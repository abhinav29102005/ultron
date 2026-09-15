"""
scripts/wakeword_tune.py – Live wake-word score meter
======================================================
Answers one question the app cannot: *what score does YOUR voice, on YOUR
microphone, in YOUR room, actually reach when you say "hey ULTRON"?*

The detector fires when a frame's score beats (1 - WAKEWORD_SENSITIVITY).
Everything below that threshold is a silent miss, so a wake word that "takes
a few tries" is invisible from inside the app. This script prints every
score spike live, tracks the peaks, and ends by recommending the .env line.

Usage (from the repo root):

    .venv/Scripts/python.exe scripts/wakeword_tune.py [seconds]

Say "hey ULTRON" 5-10 times at your normal distance and volume, in the
conditions you actually use ULTRON in. Default run time is 30 seconds.
"""

from __future__ import annotations

import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import force_utf8_output
from utils.env import load_env_file

force_utf8_output()
load_env_file()

SAMPLE_RATE = 16000
BLOCK = 1280  # 80 ms — the frame size openWakeWord expects
MODEL = "hey_jarvis"

#: Spikes below this are room noise; printing them would bury the signal.
PRINT_FLOOR = 0.10

#: A peak counts as "you said the phrase" above this. Deliberately low: the
#: point is to see weak detections, not to pre-filter them away.
PEAK_FLOOR = 0.15


def main(seconds: float) -> int:
    from openwakeword.model import Model  # slow import; see main_gui.py

    import sounddevice as sd

    sensitivity = float(os.getenv("WAKEWORD_SENSITIVITY", "0.5"))
    threshold = min(max(1.0 - sensitivity, 0.05), 0.95)

    print(f"Current WAKEWORD_SENSITIVITY={sensitivity}  ->  threshold={threshold:.2f}")
    print(f"Listening for {seconds:.0f}s — say \"hey ULTRON\" 5-10 times, normally.\n")

    model = Model(wakeword_models=[MODEL])
    audio: queue.Queue = queue.Queue(maxsize=64)

    def callback(indata, frames, _time, _status) -> None:
        try:
            audio.put_nowait(indata.copy())
        except queue.Full:
            pass

    peaks: list[float] = []
    current_peak = 0.0
    in_spike = False

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        blocksize=BLOCK,
        dtype="int16",
        callback=callback,
    )
    stream.start()
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            try:
                chunk = audio.get(timeout=0.2).flatten()
            except queue.Empty:
                continue
            score = model.predict(chunk).get(MODEL, 0.0)

            if score > PRINT_FLOOR:
                verdict = "TRIGGER" if score > threshold else "miss"
                bar = "#" * int(score * 40)
                print(f"  score {score:.2f} {bar:<40} {verdict}")

            # One utterance produces a run of elevated frames; record its max
            # once, when the run ends, rather than every frame of it.
            if score > PEAK_FLOOR:
                in_spike = True
                current_peak = max(current_peak, score)
            elif in_spike:
                peaks.append(current_peak)
                current_peak = 0.0
                in_spike = False
    finally:
        stream.stop()
        stream.close()

    if in_spike:
        peaks.append(current_peak)

    print()
    if not peaks:
        print("No spikes above 0.15 heard. Either nothing was said, the wrong")
        print("microphone is the default input device, or the input volume is")
        print("very low — check Windows sound settings before tuning further.")
        return 1

    peaks.sort()
    weakest = peaks[0]
    print(f"Heard {len(peaks)} utterance(s). Peak scores: "
          + ", ".join(f"{p:.2f}" for p in peaks))

    # Trigger on the weakest attempt with a little margin, floored so casual
    # conversation does not start waking it.
    suggested_threshold = max(weakest - 0.05, 0.15)
    suggested = round(1.0 - suggested_threshold, 2)
    hits = sum(1 for p in peaks if p > threshold)
    print(f"\nAt the current threshold {threshold:.2f}, "
          f"{hits}/{len(peaks)} of those would have triggered.")
    print(f"To catch all of them, set in .env:\n\n    WAKEWORD_SENSITIVITY={suggested}\n")
    return 0


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    sys.exit(main(duration))
