"""
utils/validators.py – Generic Input Validation Functions
=========================================================
Provides generic validation helper functions.

Team: Core Platform Team
Phase: 0 (Implementation)
"""

from __future__ import annotations

import os
from pathlib import Path
from utils.exceptions import ValidationError


def validate_env(var_name: str) -> str:
    """
    Validate that an environment variable exists and is not empty.

    Args:
        var_name: The name of the environment variable.

    Returns:
        str: The environment variable value.

    Raises:
        ValidationError: If the environment variable is missing or empty.
    """
    value = os.environ.get(var_name)
    if not value or not value.strip():
        raise ValidationError(f"Required environment variable '{var_name}' is missing or empty.")
    return value.strip()


def validate_path(path: str | Path, check_exists: bool = False) -> Path:
    """
    Validate that a path is syntactically correct, and optionally exists.

    Args:
        path: The path string or Path object to validate.
        check_exists: Whether to verify the path exists on disk.

    Returns:
        Path: The resolved absolute path.

    Raises:
        ValidationError: If path is empty or does not exist (when check_exists=True).
    """
    if not path:
        raise ValidationError("Path must not be empty.")
    try:
        resolved_path = Path(path).resolve()
    except Exception as exc:
        raise ValidationError(f"Invalid path format '{path}': {exc}") from exc

    if check_exists and not resolved_path.exists():
        raise ValidationError(f"Path does not exist: {resolved_path}")

    return resolved_path
