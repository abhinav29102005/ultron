"""
utils/env.py – .env into the process environment
=================================================
One call that every entry point makes, next to ``force_utf8_output()``.

Why this module exists
----------------------
FRIDAY reads configuration two different ways, and until this existed only one
of them saw ``.env``:

* ``config/settings.py`` is a pydantic ``BaseSettings`` with
  ``env_file=".env"``. Pydantic parses the file itself and does **not** export
  what it finds into ``os.environ``.
* ``speech/speechconfig.py`` and ``speech/wake_word/detector.py`` read plain
  ``os.getenv``, which only ever sees the real process environment.

So every ``os.getenv`` key documented in ``.env.example`` -- ``STT_MODEL``,
``STT_BEAM_SIZE``, ``SILENCE_TIMEOUT``, ``WAKEWORD_SENSITIVITY``,
``PICOVOICE_ACCESS_KEY`` -- silently fell back to its hardcoded default no
matter what the user put in ``.env``. Nothing failed; the setting simply had
no effect, which is the hardest kind of config bug to notice.

Loading here rather than at import time in ``speechconfig`` keeps the side
effect explicit and greppable, and keeps import order from deciding whether a
setting works.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str | Path = ".env") -> bool:
    """Copy ``.env`` into ``os.environ`` for the ``os.getenv`` readers.

    Real environment variables win: a value already exported by the shell is
    a deliberate per-run override and must not be clobbered by the file. This
    matches pydantic's own precedence, so both config paths agree.

    Returns True when a file was read. A missing ``.env`` is normal -- the
    defaults are meant to work -- so it is not an error.
    """
    env_path = Path(path)
    if not env_path.is_file():
        return False

    try:
        from dotenv import dotenv_values
    except ImportError:
        # python-dotenv ships as a pydantic-settings dependency; if it is
        # somehow absent, defaults still work and the app must still start.
        return False

    try:
        values = dotenv_values(env_path, encoding="utf-8")
    except OSError:
        return False

    for key, value in values.items():
        if value is not None and key not in os.environ:
            os.environ[key] = value

    return True
