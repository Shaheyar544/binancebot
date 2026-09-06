"""Tests for Backtest stress testing scenarios: flash crashes, bear regimes, and V-recoveries."""

from decimal import Decimal

import pytest

from src.backtest.stress import (
    generate_bull_trend_candles,
    generate_extreme_volatility_candles,
    generate_flash_crash_candles,
    generate_prolonged_bear_candles,
    generate_sideways_candles,
    generate_v_recovery_candles,
)


def test_generate_flash_crash_candles() -> None:
    """Flash crash generator drops price by specified percentage within N candles."""
    start_price = Decimal("2700.00")
    drop_pct = Decimal("0.10")
    candles = generate_flash_crash_candles(
        start_price=start_price,
        drop_pct=drop_pct,
        num_candles=8,
    )

    assert len(candles) == 8
    target_low = start_price * (Decimal("1.0") - drop_pct)
    min_low = min(c.low for c in candles)
    assert min_low <= target_low


def test_generate_prolonged_bear_candles() -> None:
    """Prolonged bear generator creates consistent lower lows and lower highs."""
    start_price = Decimal("2700.00")
    candles = generate_prolonged_bear_candles(start_price=start_price, num_candles=20)

    assert len(candles) == 20
    assert candles[-1].close < candles[0].close


@pytest.mark.parametrize("drop_pct", ["0.05", "0.10", "0.15", "0.20"])
def test_flash_crash_scenarios(drop_pct: str) -> None:
    """Stress test 5%, 10%, 15%, and 20% drops for accurate price decrement."""
    start_price = Decimal("2700.00")
    drop = Decimal(drop_pct)
    candles = generate_flash_crash_candles(start_price=start_price, drop_pct=drop, num_candles=8)

    assert len(candles) == 8
    target_low = start_price * (Decimal("1.0") - drop)
    assert min(c.low for c in candles) <= target_low


def test_v_recovery_scenario() -> None:
    """V-recovery drops price to trough and swiftly recovers back toward start."""
    start_price = Decimal("2700.00")
    candles = generate_v_recovery_candles(
        start_price,
        drop_pct=Decimal("0.05"),
        num_candles_down=6,
        num_candles_up=6,
    )

    assert len(candles) == 12
    # Midpoint candle is lowest
    trough_low = min(c.low for c in candles)
    assert trough_low <= start_price * Decimal("0.95")
    # End price recovers
    assert candles[-1].close > trough_low


def test_sideways_scenario() -> None:
    """Sideways scenario oscillates around mid price within defined amplitude."""
    mid_price = Decimal("2700.00")
    amplitude = Decimal("5.00")
    candles = generate_sideways_candles(mid_price=mid_price, amplitude=amplitude, num_candles=20)

    assert len(candles) == 20
    for c in candles:
        assert abs(c.close - mid_price) <= amplitude + Decimal("2.0")


def test_bull_trend_scenario() -> None:
    """Bull trend creates ascending prices."""
    start_price = Decimal("2700.00")
    candles = generate_bull_trend_candles(start_price=start_price, num_candles=25)

    assert len(candles) == 25
    assert candles[-1].close > candles[0].close


def test_extreme_volatility_scenario() -> None:
    """Extreme volatility produces wide wicks around mid price."""
    mid_price = Decimal("2700.00")
    amplitude = Decimal("30.00")
    candles = generate_extreme_volatility_candles(
        mid_price=mid_price,
        swing_amplitude=amplitude,
        num_candles=20,
    )

    assert len(candles) == 20
    for c in candles:
        assert c.high >= mid_price + Decimal("5.0")
        assert c.low <= mid_price - Decimal("5.0")
