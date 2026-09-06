"""Tests for candle continuity, gap detection, deduplication, and REST recovery."""

from decimal import Decimal

import pytest

from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.market_data.enums import MarketDataHealth
from src.market_data.gap_detector import GapDetector
from src.market_data.pipeline import MarketDataPipeline
from src.market_data.store import CanonicalCandleStore


def make_candle(open_time: int, interval_ms: int = 900000) -> Candle:
    """Helper to construct valid completed 15M candles."""
    return Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=open_time,
        open=Decimal("2700.00"),
        high=Decimal("2710.00"),
        low=Decimal("2695.00"),
        close=Decimal("2705.00"),
        volume=Decimal("100.0"),
        close_time=open_time + interval_ms - 1,
        is_closed=True,
    )


def test_continuous_candles_accepted() -> None:
    """Continuous candles produce no gap and keep health HEALTHY."""
    detector = GapDetector()
    t0 = 1700000000000  # 10:00
    t1 = t0 + 900000  # 10:15
    t2 = t1 + 900000  # 10:30

    assert detector.check_candle(make_candle(t0)) is None
    assert detector.check_candle(make_candle(t1)) is None
    assert detector.check_candle(make_candle(t2)) is None
    assert detector.health == MarketDataHealth.HEALTHY


def test_missing_candle_interval_detected() -> None:
    """A missing interval (e.g. 10:00, 10:15, 10:45) triggers gap detection."""
    detector = GapDetector()
    t0 = 1700000000000  # 10:00
    t1 = t0 + 900000  # 10:15
    t3 = t0 + 900000 * 3  # 10:45 (skipped 10:30)

    detector.check_candle(make_candle(t0))
    detector.check_candle(make_candle(t1))
    gap = detector.check_candle(make_candle(t3))

    assert gap is not None
    assert gap.symbol == "XAUUSDT"
    assert gap.timeframe == Timeframe.M15
    assert gap.expected_open_time == t0 + 900000 * 2  # 10:30
    assert gap.actual_open_time == t3
    assert detector.health == MarketDataHealth.GAP_DETECTED


def test_duplicate_candle_is_handled_idempotently() -> None:
    """Duplicate candles with the same open_time are ignored without raising a gap."""
    store = CanonicalCandleStore()
    c1 = make_candle(1700000000000)

    store.add_candle(c1)
    store.add_candle(c1)  # Duplicate

    candles = store.get_completed_candles(Timeframe.M15)
    assert len(candles) == 1


def test_out_of_order_candle_handling() -> None:
    """Out-of-order candles are sorted chronologically in the store."""
    store = CanonicalCandleStore()
    t0 = 1700000000000
    t1 = t0 + 900000
    t2 = t1 + 900000

    store.add_candle(make_candle(t2))
    store.add_candle(make_candle(t0))
    store.add_candle(make_candle(t1))

    candles = store.get_completed_candles(Timeframe.M15)
    assert [c.open_time for c in candles] == [t0, t1, t2]


@pytest.mark.asyncio
async def test_pipeline_recovers_gap_via_backfill() -> None:
    """When a gap is detected, pipeline recovers missing candles and restores HEALTHY."""
    pipeline = MarketDataPipeline(symbol="XAUUSDT")
    t0 = 1700000000000  # 10:00
    t1 = t0 + 900000  # 10:15
    t2 = t1 + 900000  # 10:30 (missing initially)
    t3 = t2 + 900000  # 10:45

    pipeline.ingest_completed_candle(make_candle(t0))
    pipeline.ingest_completed_candle(make_candle(t1))
    pipeline.ingest_completed_candle(make_candle(t3))
    initial_health = pipeline.health
    assert initial_health == MarketDataHealth.GAP_DETECTED

    # Simulate backfilling the missing candle
    await pipeline.backfill_candle(make_candle(t2))

    recovered_health = pipeline.health
    assert recovered_health == MarketDataHealth.HEALTHY
    completed = pipeline.get_completed_candles(Timeframe.M15)
    assert len(completed) == 4
    assert [c.open_time for c in completed] == [t0, t1, t2, t3]
