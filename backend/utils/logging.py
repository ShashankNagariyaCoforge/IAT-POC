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
    Logs to both stdout and a rotating process.log file in the backend directory.

    Args:
        log_level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Remove existing handlers
    root_logger.handlers.clear()

    # JSON formatter for stdout (structured, for Azure Monitor)
    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # stdout handler (JSON)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(json_formatter)
    root_logger.addHandler(stream_handler)

    # Silence noisy third-party loggers
    for noisy in ["azure.core", "azure.identity", "httpx", "httpcore", "asyncio"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)
