"""
utils/helpers.py – General-Purpose Utility Helpers
===================================================
Provides stateless generic helper functions.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


def project_root() -> Path:
    """
    Get the absolute Path of the project root directory.

    Returns:
        Path: The absolute path to the project root directory.
    """
    return Path(__file__).resolve().parent.parent


def current_timestamp() -> float:
    """
    Get the current Unix epoch time in seconds.

    Returns:
        float: Current UTC timestamp.
    """
    return time.time()


def platform_name() -> str:
    """
    Get the name of the operating system platform.

    Returns:
        str: Operating system identifier (e.g. 'darwin', 'linux', 'win32').
    """
    return sys.platform
