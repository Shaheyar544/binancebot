"""Tests for secret masking, redaction, and logging safety."""

import io
import logging

from src.utils.logging import configure_logging
from src.utils.security import RedactingFilter, mask_secret


def test_mask_secret() -> None:
    """mask_secret masks all but first 2 and last 2 characters for keys >= 8 chars."""
    assert mask_secret("abcdef123456") == "ab********56"
    assert mask_secret("short") == "******"
    assert mask_secret("") == "******"


def test_redacting_filter_redacts_registered_secrets() -> None:
    """Registered secrets must be replaced with [REDACTED] in logs."""
    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    secret_key = "super_secret_binance_key_999"
    redacting_filter = RedactingFilter(secrets=[secret_key])

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.addFilter(redacting_filter)
    logger.addHandler(handler)

    logger.info("Initializing connection with key: %s", secret_key)
    output = log_stream.getvalue()

    assert secret_key not in output
    assert "[REDACTED]" in output


def test_global_logging_configuration_masks_secrets() -> None:
    """configure_logging installs redaction filter and redacts sensitive patterns."""
    secret = "secret_trading_token_xyz"
    configure_logging(log_level="DEBUG", secrets_to_redact=[secret])

    logger = logging.getLogger("xau_test")
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    for f in logging.getLogger().handlers[0].filters:
        handler.addFilter(f)
    logger.addHandler(handler)

    logger.info("Using token %s to authenticate", secret)
    output = log_stream.getvalue()

    assert secret not in output
