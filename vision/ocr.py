"""
vision/ocr.py – Reading characters, shared between the callers that need them
=============================================================================
Two paths now want the *exact* characters out of an image rather than a
model's description of them: ``skills/screen_text_skill.py`` (a
full-resolution grab of the monitor) and a screenshot pasted into the chat
panel. Both used to be served by a private helper inside the skill; the paste
path is UI code and has no business importing a skill to read an image, so the
engine moved here.

Sharing matters for one concrete reason: constructing ``RapidOCR`` loads three
ONNX models from disk and costs a couple of seconds. A second engine would pay
that twice and hold two copies resident for the life of the process.

RapidOCR rather than Tesseract on purpose: it is a pip install with bundled
models and needs no system binary on the user's PATH, which on Windows is the
difference between working and not.
"""

from __future__ import annotations

import io

from config.logging_config import get_logger

logger = get_logger("vision.ocr")

__all__ = ["engine", "ocr_lines", "run_ocr"]

_CACHED_ENGINE = None


def engine():
    """One RapidOCR instance, reused.

    Constructing it loads three ONNX models from disk and costs a couple of
    seconds — far too long to pay on every question about the screen, and
    unacceptable on a paste, where the user is watching the cursor blink.

    The import is deferred so that importing this module never requires the
    OCR package; callers turn the :class:`ImportError` into an install hint.
    """
    global _CACHED_ENGINE
    if _CACHED_ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR

        _CACHED_ENGINE = RapidOCR()
    return _CACHED_ENGINE


def ocr_lines(png: bytes) -> list[str]:
    """Recognised lines, top to bottom."""
    import numpy as np
    from PIL import Image

    image = np.array(Image.open(io.BytesIO(png)).convert("RGB"))

    result, _elapsed = engine()(image)

    if not result:
        return []

    # Each entry is [box, text, confidence]; box[0] is the top-left corner.
    # Sorting by y then x recovers reading order, which the detector does not
    # guarantee and which matters for a stack trace.
    ordered = sorted(result, key=lambda item: (round(item[0][0][1] / 10), item[0][0][0]))
    return [str(item[1]).rstrip() for item in ordered if str(item[1]).strip()]


def run_ocr(png: bytes) -> str:
    """Everything recognised in ``png`` as one block of text.

    The line list is the useful form for a transcript the user reads back; a
    single string is the useful form for the two things the paste path does
    with it — measure it, and drop it into a prompt.
    """
    return "\n".join(ocr_lines(png))
