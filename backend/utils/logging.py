"""
Structured JSON logging setup.
Uses python-json-logger for consistent, parseable log output
suitable for Azure Monitor log ingestion.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger with JSON formatter for all application logging.
    Logs to both stdout and a rotating process.log file in the backend directory.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Readable plain-text formatter for the log file
    plain_formatter = logging.Formatter(
        fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # JSON formatter for stdout (structured, for Azure Monitor)
    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # stdout handler (JSON)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(json_formatter)
    root_logger.addHandler(stream_handler)

    # Rotating file handler — process.log next to main.py, max 10 MB, keep 3 backups
    log_path = Path(__file__).resolve().parent.parent / "process.log"
    file_handler = RotatingFileHandler(
        log_path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(plain_formatter)
    root_logger.addHandler(file_handler)

    # Silence noisy third-party loggers
    for noisy in ["azure.core", "azure.identity", "httpx", "httpcore", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
