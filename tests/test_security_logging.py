"""Tests for secret masking, redaction, and logging safety."""

import io
import logging
from decimal import Decimal

from pydantic import SecretStr

from src.config.settings import BotConfig, UserRiskConfig
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


def test_embedded_secret_inside_larger_string_is_redacted() -> None:
    """Secrets embedded inside URLs, json dumps, or complex messages must be redacted."""
    raw_secret = "my_hidden_signing_secret_xyz"
    redacting_filter = RedactingFilter(secrets=[raw_secret])

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname="test.py",
        lineno=10,
        msg=f"Error posting request to https://api.binance.com/order?signature={raw_secret}&symbol=XAUUSDT",
        args=(),
        exc_info=None,
    )
    redacting_filter.filter(record)
    assert raw_secret not in record.msg
    assert "[REDACTED]" in record.msg


def test_secrets_hidden_from_repr() -> None:
    """BotConfig must use SecretStr so that repr() never leaks raw secrets."""
    secret_key = "api_key_12345678"
    secret_token = "secret_token_87654321"

    config = BotConfig(
        risk=UserRiskConfig(
            allocated_funds=Decimal("1000.00"),
            leverage=Decimal("3.0"),
            max_acceptable_liquidation_price=Decimal("1800.00"),
        ),
        binance_api_key=SecretStr(secret_key),
        binance_api_secret=SecretStr(secret_token),
    )

    repr_str = repr(config)
    str_str = str(config)

    assert secret_key not in repr_str
    assert secret_token not in repr_str
    assert secret_key not in str_str
    assert secret_token not in str_str
    assert "**********" in repr_str or "[REDACTED]" in repr_str


def test_global_logging_configuration_masks_secrets() -> None:
    """configure_logging installs redaction filter and redacts sensitive patterns."""
    secret = "secret_trading_token_xyz"
    configure_logging(log_level="DEBUG", secrets_to_redact=[secret])

    logger = logging.getLogger("xau_test_global")
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    for f in logging.getLogger().handlers[0].filters:
        handler.addFilter(f)
    logger.addHandler(handler)

    logger.info("Using token %s to authenticate", secret)
    output = log_stream.getvalue()

    assert secret not in output
    assert "[REDACTED]" in output
