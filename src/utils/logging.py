"""Logging configuration with secret redaction and structured formatting."""

import logging
import sys

from src.utils.security import RedactingFilter

_GLOBAL_REDACTING_FILTER = RedactingFilter()


def configure_logging(log_level: str = "INFO", secrets_to_redact: list[str] | None = None) -> None:
    """Configure system-wide logging with automatic secret scrubbing."""
    if secrets_to_redact:
        for secret in secrets_to_redact:
            _GLOBAL_REDACTING_FILTER.add_secret(secret)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    handler.addFilter(_GLOBAL_REDACTING_FILTER)
    root_logger.addHandler(handler)


def register_secret(secret: str) -> None:
    """Dynamically register a secret to be scrubbed from all logs."""
    _GLOBAL_REDACTING_FILTER.add_secret(secret)
