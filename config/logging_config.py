"""
config/logging_config.py – Loguru Logging Configuration
========================================================
Configures Loguru handlers for stdout and rotating file logging.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import sys
from pathlib import Path
try:
    from loguru import logger
except ImportError:
    import logging

    class _FallbackLogger:
        def __init__(self, name: str = "ultron"):
            self._logger = logging.getLogger(name)

        def bind(self, **kwargs):
            name = kwargs.get("name", "ultron")
            return logging.getLogger(name)

        def debug(self, msg, *args, **kwargs):
            self._logger.debug(msg, *args, **kwargs)

        def info(self, msg, *args, **kwargs):
            self._logger.info(msg, *args, **kwargs)

        def warning(self, msg, *args, **kwargs):
            self._logger.warning(msg, *args, **kwargs)

        def error(self, msg, *args, **kwargs):
            self._logger.error(msg, *args, **kwargs)

        def remove(self, *args, **kwargs):
            pass

        def add(self, *args, **kwargs):
            pass

    logger = _FallbackLogger()
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """
    Configure Loguru handlers. Removes standard configuration and sets up console
    and rotating file outputs.

    Args:
        settings: Application Settings containing log_level and log_dir.
    """
    # Remove all default handlers (including default stderr logger)
    logger.remove()

    log_level = "DEBUG" if settings.debug else settings.log_level.upper()

    # 1. Console Logging Handler - Suppressed to ERROR to prevent CLI cluttering
    #    pythonw.exe - which is what the autostart launcher runs - has no
    #    console, so sys.stderr is None there and loguru rejects it as a sink.
    #    Skip the console rather than fail startup: the file handler below is
    #    the only record a windowless process leaves behind, and it is the one
    #    that matters.
    if sys.stderr is not None:
        logger.add(
            sys.stderr,
            level="ERROR",
            format="[{level}] {message}",
            enqueue=False
        )

    # 2. File Logging Handler - Keeps detailed timestamped format
    log_file_path = Path(settings.log_dir) / "ultron.log"
    logger.add(
        str(log_file_path),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="10 MB",
        retention="5 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8"
    )


def get_logger(name: str):
    """
    Get a logger bound to a specific module name.
    """
    return logger.bind(name=name)
