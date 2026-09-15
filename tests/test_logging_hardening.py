"""
tests/test_logging_hardening.py – Two ways the logger stopped telling the truth
===============================================================================
Both bugs are silent by construction, which is why neither was caught: one
only fires in a process with no console, and the other only ever damages the
log line it was supposed to write.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path

import pytest
from loguru import logger

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def clean_logger():
    """configure_logging() calls logger.remove(). Put the global logger back
    afterwards, and close the tmp_path file handler so Windows can delete it."""
    try:
        yield
    finally:
        logger.remove()
        logger.add(sys.stderr, level="ERROR")


def _settings(log_dir: Path) -> types.SimpleNamespace:
    return types.SimpleNamespace(debug=False, log_level="INFO", log_dir=str(log_dir))


# ── 1. a process with no console ──────────────────────────────────────────────
class TestConsoleHandlerWithoutStderr:
    """Under ``pythonw.exe`` — which is what the autostart launcher runs —
    ``sys.stderr`` is None. loguru refuses a None sink, so configure_logging
    raised before it reached the file handler and ULTRON never started at
    login. See logs/autostart_launcher.log, 2026-08-26T16:23."""

    def test_configure_logging_survives_a_missing_stderr(
        self, monkeypatch, tmp_path, clean_logger
    ) -> None:
        from config.logging_config import configure_logging

        monkeypatch.setattr(sys, "stderr", None)

        configure_logging(_settings(tmp_path))  # must not raise

    def test_the_file_handler_is_still_installed(
        self, monkeypatch, tmp_path, clean_logger
    ) -> None:
        """Losing the console is survivable. Losing the log file is not —
        it is the only record a windowless process leaves behind."""
        from config.logging_config import configure_logging

        monkeypatch.setattr(sys, "stderr", None)
        configure_logging(_settings(tmp_path))

        logger.info("hello from a windowless process")
        logger.complete()

        log_file = tmp_path / "ULTRON.log"
        assert log_file.is_file(), "no log file was created without a stderr"
        assert "hello from a windowless process" in log_file.read_text(
            encoding="utf-8"
        )

    def test_a_real_stderr_is_still_used(self, tmp_path, clean_logger) -> None:
        """The guard must skip the console handler only when there is no
        console — not disable it for everyone."""
        from config.logging_config import configure_logging

        written: list[str] = []

        class FakeStderr:
            def write(self, text: str) -> None:
                written.append(text)

            def flush(self) -> None:
                pass

        import config.logging_config as logging_config

        original = logging_config.sys.stderr
        try:
            logging_config.sys.stderr = FakeStderr()
            configure_logging(_settings(tmp_path))
            logger.error("this one is loud enough for the console")
            logger.complete()
        finally:
            logging_config.sys.stderr = original

        assert any("this one is loud enough" in chunk for chunk in written), (
            "the console handler was dropped even though stderr existed"
        )


# ── 2. printf placeholders in a str.format logger ─────────────────────────────
PRINTF_CALL = re.compile(
    r"logger\.(?:debug|info|success|warning|error|exception|critical)\("
    r"[^)]*%[sdrifxg]"
)

SOURCE_DIRS = (
    "core",
    "config",
    "intelligence",
    "llm",
    "memory",
    "skills",
    "speech",
    "ui",
    "utils",
    "vision",
)


def _source_files() -> list[Path]:
    files = [
        path
        for directory in SOURCE_DIRS
        for path in (REPO_ROOT / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    files += [REPO_ROOT / name for name in ("main.py", "main_gui.py", "run.py")]
    return [path for path in files if path.is_file()]


class TestLogPlaceholders:
    """loguru interpolates with ``str.format``, not printf. Given
    ``logger.info("loaded %s", model)`` it calls ``"loaded %s".format(model)``,
    which finds no ``{}``, discards the argument, and logs a literal ``%s`` —
    exactly what logs/ULTRON.log recorded on 2026-08-25."""

    def test_no_source_file_uses_printf_placeholders(self) -> None:
        offenders = [
            f"{path.relative_to(REPO_ROOT).as_posix()}:{number}: {line.strip()}"
            for path in _source_files()
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            )
            if PRINTF_CALL.search(line)
        ]

        assert not offenders, (
            "loguru uses {} placeholders; these calls drop their arguments:\n"
            + "\n".join(offenders)
        )

    @pytest.mark.asyncio
    async def test_the_preload_line_names_the_model(
        self, monkeypatch, clean_logger
    ) -> None:
        """The behaviour behind the static check: a real call path must put
        the value in the line, not the placeholder."""
        import vision.vision_client as vision_client

        class FakeClient:
            async def chat(self, **kwargs):
                return {}

        monkeypatch.setattr(vision_client, "_client", lambda host: FakeClient())

        captured: list[str] = []
        logger.remove()
        logger.add(captured.append, level="DEBUG", format="{message}")

        assert await vision_client.preload("testvision:3b", "http://x", "45m") is True
        logger.complete()

        line = "".join(captured)
        assert "%s" not in line, f"placeholder survived into the log: {line!r}"
        assert "testvision:3b" in line, f"model name never reached the log: {line!r}"
        assert "45m" in line, f"keep_alive never reached the log: {line!r}"
