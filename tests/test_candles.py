"""Tests for candle normalization, integrity, and completed candle store."""

from decimal import Decimal

import pytest

from src.domain.enums import Timeframe
from src.market_data.normalizer import CandleNormalizer
from src.market_data.store import CanonicalCandleStore
from tests.fixtures.binance_fixtures import (
    KLINES_RAW_15M,
    WS_KLINE_PAYLOAD_CLOSED,
    WS_KLINE_PAYLOAD_OPEN,
)


def test_normalize_rest_klines() -> None:
    """REST raw kline array must normalize into immutable Candle models with Decimals."""
    normalizer = CandleNormalizer()
    candles = [normalizer.from_rest_raw("XAUUSDT", Timeframe.M15, k) for k in KLINES_RAW_15M]

    assert len(candles) == 3
    first = candles[0]
    assert first.symbol == "XAUUSDT"
    assert first.timeframe == Timeframe.M15
    assert first.open_time == 1700000000000
    assert first.open == Decimal("2700.00")
    assert first.high == Decimal("2710.50")
    assert first.low == Decimal("2695.20")
    assert first.close == Decimal("2705.00")
    assert first.volume == Decimal("150.250")
    assert first.close_time == 1700000899999
    assert first.is_closed is True

    assert isinstance(first.open, Decimal)
    assert isinstance(first.volume, Decimal)


def test_normalize_websocket_closed_kline() -> None:
    """WebSocket kline with x=True normalizes to a completed Candle."""
    normalizer = CandleNormalizer()
    candle = normalizer.from_ws_payload(WS_KLINE_PAYLOAD_CLOSED)

    assert candle.symbol == "XAUUSDT"
    assert candle.timeframe == Timeframe.M15
    assert candle.is_closed is True
    assert candle.open == Decimal("2700.00")
    assert candle.close == Decimal("2705.00")


def test_normalize_websocket_open_kline() -> None:
    """WebSocket kline with x=False normalizes to an in-progress candle with is_closed=False."""
    normalizer = CandleNormalizer()
    candle = normalizer.from_ws_payload(WS_KLINE_PAYLOAD_OPEN)

    assert candle.symbol == "XAUUSDT"
    assert candle.is_closed is False
    with pytest.raises(ValueError, match="Incomplete candle cannot be used"):
        candle.assert_completed()


def test_completed_candle_store_rejects_incomplete_candle() -> None:
    """CanonicalCandleStore strictly rejects incomplete candles."""
    store = CanonicalCandleStore()
    normalizer = CandleNormalizer()
    open_candle = normalizer.from_ws_payload(WS_KLINE_PAYLOAD_OPEN)

    with pytest.raises(ValueError, match="Incomplete candle cannot enter canonical store"):
        store.add_candle(open_candle)

    assert len(store.get_completed_candles(Timeframe.M15)) == 0


def test_completed_candle_store_accepts_and_orders_candles() -> None:
    """CanonicalCandleStore accepts completed candles and maintains chronological order."""
    store = CanonicalCandleStore()
    normalizer = CandleNormalizer()
    closed_candle = normalizer.from_ws_payload(WS_KLINE_PAYLOAD_CLOSED)

    store.add_candle(closed_candle)
    completed = store.get_completed_candles(Timeframe.M15)
    assert len(completed) == 1
    assert completed[0].open_time == 1700000000000
    assert store.latest_completed(Timeframe.M15) == closed_candle
