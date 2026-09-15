"""
speech/wake_word/detector.py – Wake Word Detection (Porcupine + openWakeWord fallback)
===================================================================================
Uses Porcupine (pvporcupine) as primary engine; falls back to openWakeWord
if available. Porcupine works on Windows without tflite-runtime.
"""

from __future__ import annotations

import queue
import threading
import os

import numpy as np
import sounddevice as sd

from config.logging_config import get_logger
from speech.audio_bus import MIC, MicBusy

logger = get_logger("wakeword")

try:
    import pvporcupine
except Exception:
    pvporcupine = None

try:
    from openwakeword.model import Model as OWWModel
except Exception:
    OWWModel = None

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 512  # Porcupine expects 512 samples at 16kHz

# Porcupine settings
PORCUPINE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
# Porcupine only accepts its own built-in keyword names. "ULTRON" is NOT one
# of them, and the name is "hey google" with a space -- the previous list
# ("ULTRON", "hey_google") made pvporcupine.create() raise, which silently
# dropped us back to openWakeWord even when a valid key was configured.
# Override with WAKEWORD_KEYWORDS (comma separated) or point
# PORCUPINE_KEYWORD_PATH at a custom .ppn from the Picovoice console.
_DEFAULT_PORCUPINE_KEYWORDS = ["ULTRON", "computer"]
PORCUPINE_KEYWORDS = [
    k.strip() for k in os.getenv(
        "WAKEWORD_KEYWORDS", ",".join(_DEFAULT_PORCUPINE_KEYWORDS)
    ).split(",") if k.strip()
]
PORCUPINE_KEYWORD_PATH = os.getenv("PORCUPINE_KEYWORD_PATH", "")
PORCUPINE_SENSITIVITY = float(os.getenv("WAKEWORD_SENSITIVITY", "0.5"))

# openWakeWord fallback
OWW_MODEL = "hey_jarvis"


def _oww_threshold(sensitivity: float) -> float:
    """Map the user-facing sensitivity knob to an openWakeWord score threshold.

    WAKEWORD_SENSITIVITY reads "higher = easier to trigger" — Porcupine's
    convention, and the one a user guesses. openWakeWord's threshold is the
    inverse: a score the phrase must *beat*. This maps one onto the other so
    the same .env line tunes whichever engine is active. The clamp keeps a
    typo'd value from producing an always-on (0.0) or never-fires (1.0) wake
    word.

    Before this existed the threshold was a hardcoded 0.5 and the .env knob
    silently tuned an engine that was not running — on a laptop microphone at
    conversational distance "hey ULTRON" peaks in the 0.3-0.5 band often
    enough that 0.5 reads as "it takes a few tries".
    """
    try:
        value = 1.0 - float(sensitivity)
    except (TypeError, ValueError):
        return 0.5
    return min(max(value, 0.05), 0.95)


OWW_THRESHOLD = _oww_threshold(os.getenv("WAKEWORD_SENSITIVITY", "0.5"))

#: Scores above this but below the threshold are logged: they are the phrase
#: being heard and rejected, which is exactly what threshold tuning needs to
#: see and exactly what a silent miss otherwise hides.
OWW_NEAR_MISS = 0.2


class WakeWordDetector:
    """Wake word detector with Porcupine primary, openWakeWord fallback."""

    def __init__(self) -> None:
        self._porcupine = None
        self._oww = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=64)
        self._stop_event = threading.Event()
        # Set only once the detect loop's stream is genuinely closed. Callers
        # that are about to open the microphone themselves must wait on this;
        # stop() alone returns long before the stream is gone.
        self._closed_event = threading.Event()
        self._closed_event.set()
        self._engine = "none"
        #: True after a positive detection: the phrase that triggered is
        #: still in the openWakeWord buffer and must be cleared before the
        #: next detect() or it triggers again. See _detect_oww for why the
        #: reset is not simply done on every entry.
        self._oww_reset_pending = True

        # Try Porcupine first
        if pvporcupine is not None and PORCUPINE_ACCESS_KEY:
            try:
                if PORCUPINE_KEYWORD_PATH:
                    # A custom phrase trained in the Picovoice console -- the
                    # only way to get a wake word Porcupine has no built-in for
                    # (e.g. "hey ULTRON").
                    paths = [
                        p.strip()
                        for p in PORCUPINE_KEYWORD_PATH.split(";")
                        if p.strip()
                    ]
                    missing = [p for p in paths if not os.path.isfile(p)]
                    if missing:
                        raise FileNotFoundError(
                            f"PORCUPINE_KEYWORD_PATH not found: {missing}"
                        )
                    self._porcupine = pvporcupine.create(
                        access_key=PORCUPINE_ACCESS_KEY,
                        keyword_paths=paths,
                        sensitivities=[PORCUPINE_SENSITIVITY] * len(paths),
                    )
                    label = [os.path.splitext(os.path.basename(p))[0] for p in paths]
                else:
                    unknown = [
                        k for k in PORCUPINE_KEYWORDS
                        if k not in pvporcupine.KEYWORDS
                    ]
                    if unknown:
                        raise ValueError(
                            f"Not Porcupine built-in keywords: {unknown}. "
                            f"Available: {sorted(pvporcupine.KEYWORDS)}. "
                            f"For a custom phrase set PORCUPINE_KEYWORD_PATH."
                        )
                    self._porcupine = pvporcupine.create(
                        access_key=PORCUPINE_ACCESS_KEY,
                        keywords=PORCUPINE_KEYWORDS,
                        sensitivities=[PORCUPINE_SENSITIVITY] * len(PORCUPINE_KEYWORDS),
                    )
                    label = PORCUPINE_KEYWORDS
                self._engine = "porcupine"
                print(f"Wake word engine: Porcupine (keywords: {label})")
            except Exception as e:
                print(f"Porcupine init failed: {e}")
                self._porcupine = None

        # Fallback to openWakeWord
        if self._porcupine is None and OWWModel is not None:
            try:
                self._oww = OWWModel(wakeword_models=[OWW_MODEL])
                self._engine = "openwakeword"
                print(f"Wake word engine: openWakeWord ({OWW_MODEL})")
            except Exception as e:
                print(f"openWakeWord init failed: {e}")
                self._oww = None

        if self._engine == "none":
            print("Wake word: NO ENGINE AVAILABLE (set PICOVOICE_ACCESS_KEY for Porcupine)")

    def stop(self) -> None:
        """Ask the detect loop to finish. Returns before the stream is closed.

        The stop stays in force until :meth:`resume` clears it. ``detect()``
        used to clear the flag on entry, which silently swallowed a stop that
        arrived between two iterations of the caller's loop — so the detector
        kept the microphone and the recorder could not get it.
        """
        self._stop_event.set()

    def resume(self) -> None:
        """Lift a previous stop, allowing detect() to open the device again."""
        self._stop_event.clear()

    def wait_closed(self, timeout: float = 2.0) -> bool:
        """Block until the detect loop has actually closed its input stream.

        ``stop()`` only sets an event; the stream is closed afterwards, on the
        detector's own thread. Opening the recorder without waiting here puts
        two input streams on one device, which is the PortAudio input overflow
        that used to kill the app on barge-in.
        """
        return self._closed_event.wait(timeout)

    def _callback(self, indata, frames, time, status):
        if status:
            # Never printed: this fires from the audio thread and would spam
            # the console during a conversation.
            pass
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            # A wake word is detected from live audio; a backlog is useless.
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(indata.copy())
            except (queue.Empty, queue.Full):
                pass

    def detect(self) -> bool:
        """Blocks until wake word heard or stop() called. Returns True if heard."""
        if self._engine == "none":
            self._stop_event.wait(0.2)
            return False

        # A stop that is still in force means someone else wants the device.
        # Opening a stream here is what put two of them on one input.
        if self._stop_event.is_set():
            return False

        self._closed_event.clear()

        try:
            # Stand down rather than fight the recorder for the device. The
            # caller loops, so a miss here just means we try again shortly.
            try:
                token = MIC.acquire("wake_word", timeout=0.5)
            except MicBusy:
                self._stop_event.wait(0.2)
                return False

            try:
                if self._engine == "porcupine":
                    return self._detect_porcupine()
                if self._engine == "openwakeword":
                    return self._detect_oww()
                return False
            finally:
                MIC.release(token)
        finally:
            self._closed_event.set()

    def _detect_porcupine(self) -> bool:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=CHUNK_SAMPLES,
            dtype="int16",
            callback=self._callback,
        )
        stream.start()
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.2).flatten()
                except queue.Empty:
                    continue
                keyword_index = self._porcupine.process(chunk)
                if keyword_index >= 0:
                    return True
            return False
        finally:
            stream.stop()
            stream.close()
            self._audio_queue.queue.clear()

    def _detect_oww(self) -> bool:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            blocksize=1280,
            dtype="int16",
            callback=self._callback,
        )
        stream.start()
        # Reset only after a *detection*, not on every entry. The reset
        # exists so the "hey ULTRON" still sitting in the model's buffer
        # cannot trigger twice. Wiping the buffer on every call meant every
        # pause/resume cycle re-entered with ~1s of cold, meaningless scores
        # — and a user who speaks the moment ULTRON resumes listening lands
        # exactly inside that window, which reads as "it ignored me".
        if self._oww_reset_pending:
            self._oww.reset()
            self._oww_reset_pending = False
        peak = 0.0
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.2).flatten()
                except queue.Empty:
                    continue
                score = self._oww.predict(chunk).get(OWW_MODEL, 0.0)
                if score > peak:
                    peak = score
                if score > OWW_THRESHOLD:
                    logger.debug(
                        "Wake word heard (score {:.2f} > threshold {:.2f})",
                        score,
                        OWW_THRESHOLD,
                    )
                    self._oww_reset_pending = True
                    return True
            if peak > OWW_NEAR_MISS:
                # The phrase was heard and rejected. Silent misses are what
                # make the wake word feel broken; this line is what turns
                # "say it again" into a threshold number someone can tune.
                logger.info(
                    "Wake word near miss: peak score {:.2f}, threshold {:.2f}. "
                    "Raise WAKEWORD_SENSITIVITY in .env to trigger easier.",
                    peak,
                    OWW_THRESHOLD,
                )
            return False
        finally:
            stream.stop()
            stream.close()
            self._audio_queue.queue.clear()