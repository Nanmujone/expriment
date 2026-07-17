"""Rotating diagnostic logs that redact before formatting reaches disk."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .redaction import SensitiveDataScanner


class _RedactingFilter(logging.Filter):
    def __init__(self, scanner: SensitiveDataScanner) -> None:
        super().__init__()
        self._scanner = scanner

    def filter(self, record: logging.LogRecord) -> bool:
        message = self._scanner.redact(record.getMessage())
        if record.exc_info is not None:
            message = f"{message} [exception details omitted]"
            record.exc_info = None
            record.exc_text = None
        record.msg = message
        record.args = ()
        return True


def configure_diagnostic_logger(
    log_path: Path,
    scanner: SensitiveDataScanner,
    *,
    max_bytes: int = 2 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """Create an isolated rotating logger with mandatory pre-write redaction."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if backup_count < 0:
        raise ValueError("backup_count cannot be negative")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"english_player.diagnostics.{log_path.resolve()}")
    close_diagnostic_logger(logger)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.addFilter(_RedactingFilter(scanner))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


def close_diagnostic_logger(logger: logging.Logger) -> None:
    """Flush, close, and detach every handler owned by a diagnostic logger."""

    for handler in tuple(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)
