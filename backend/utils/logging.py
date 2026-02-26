"""
Structured JSON logging setup.
Uses python-json-logger for consistent, parseable log output
suitable for Azure Monitor log ingestion.
"""

import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure root logger with JSON formatter for all application logging.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # JSON formatter for structured log output
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    for noisy in ["azure.core", "azure.identity", "httpx", "httpcore", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
