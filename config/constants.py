"""
config/constants.py – Immutable Application Constants
======================================================
Stores general constants used across the application.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

# Application Metadata
APP_NAME: str = "FRIDAY"
APP_VERSION: str = "0.1.0"

# Defaults
DEFAULT_LOG_FILE: str = "friday.log"
DEFAULT_ENV_FILE: str = ".env"

# Event Bus Settings
DEFAULT_EVENT_LOOP_DELAY: float = 0.01
