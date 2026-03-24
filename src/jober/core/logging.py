"""Persistent file logging for JOBer."""

from __future__ import annotations

import os

from loguru import logger as _logger

from jober.core.config import JOBER_HOME


LOGS_DIR = JOBER_HOME / "logs"
LOG_FILE = LOGS_DIR / "jober.log"
_CONFIGURED = False


def configure_logging() -> None:
    """Configure the shared file logger once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _logger.remove()
    _logger.add(
        LOG_FILE,
        level=os.getenv("JOBER_LOG_LEVEL", "DEBUG"),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {name}:{function}:{line} | {message}",
        encoding="utf-8",
        rotation="5 MB",
        retention="14 days",
        backtrace=True,
        diagnose=True,
        enqueue=False,
    )
    _CONFIGURED = True


configure_logging()
logger = _logger


__all__ = ["LOGS_DIR", "LOG_FILE", "configure_logging", "logger"]
