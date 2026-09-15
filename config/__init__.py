"""
config/__init__.py – Configuration Package
===========================================
The ``config`` package centralises all application configuration for
ULTRON, including:

  - Environment-driven settings (via Pydantic Settings)
  - Application-wide constants
  - Structured logging configuration

Public surface:
    - :class:`~config.settings.Settings`
    - :func:`~config.logging_config.configure_logging`
    - :mod:`~config.constants`
"""

from config.settings import Settings

__all__: list[str] = ["Settings"]
