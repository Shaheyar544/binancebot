"""Tests for price streams (last, mark, index prices) and staleness detection."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.market_data.enums import PriceType
from src.market_data.models import PriceUpdate
from tests.fixtures.binance_fixtures import PREMIUM_INDEX_RAW, TICKER_PRICE_RAW


def test_parse_last_price_from_ticker() -> None:
    """Ticker last price parses into PriceUpdate with Decimal precision."""
    update = PriceUpdate.from_ticker_raw(TICKER_PRICE_RAW, local_receive_time=1700000900100)
    assert update.symbol == "XAUUSDT"
    assert update.price_type == PriceType.LAST
    assert update.price == Decimal("2705.10")
    assert isinstance(update.price, Decimal)
    assert update.exchange_timestamp == 1700000900000
    assert update.local_receive_timestamp == 1700000900100


def test_parse_mark_and_index_prices() -> None:
    """Premium index endpoint produces distinct mark and index prices."""
    mark_update = PriceUpdate.from_premium_index_raw(
        PREMIUM_INDEX_RAW, price_type=PriceType.MARK, local_receive_time=1700000900050
    )
    index_update = PriceUpdate.from_premium_index_raw(
        PREMIUM_INDEX_RAW, price_type=PriceType.INDEX, local_receive_time=1700000900050
    )

    assert mark_update.price == Decimal("2704.80000000")
    assert index_update.price == Decimal("2704.50000000")
    assert mark_update.price != index_update.price


def test_reject_zero_or_negative_price() -> None:
    """Invalid non-positive prices must be rejected."""
    with pytest.raises(ValidationError):
        PriceUpdate(
            symbol="XAUUSDT",
            price_type=PriceType.LAST,
            price=Decimal("0.00"),
            exchange_timestamp=1700000000000,
            local_receive_timestamp=1700000000100,
        )
    with pytest.raises(ValidationError):
        PriceUpdate(
            symbol="XAUUSDT",
            price_type=PriceType.LAST,
            price=Decimal("-10.00"),
            exchange_timestamp=1700000000000,
            local_receive_timestamp=1700000000100,
        )


def test_stale_price_detection() -> None:
    """Staleness check detects when price timestamp exceeds freshness threshold."""
    update = PriceUpdate(
        symbol="XAUUSDT",
        price_type=PriceType.MARK,
        price=Decimal("2700.00"),
        exchange_timestamp=1700000000000,
        local_receive_timestamp=1700000000050,
    )
    # Threshold: 5000ms (5 seconds)
    # 3 seconds later -> not stale
    assert update.is_stale(current_time_ms=1700000003000, threshold_ms=5000) is False

    # 6 seconds later -> stale
    assert update.is_stale(current_time_ms=1700000006000, threshold_ms=5000) is True
