"""Tests for Backtest stress testing scenarios: flash crashes, bear regimes, and V-recoveries."""

from decimal import Decimal

from src.backtest.stress import generate_flash_crash_candles, generate_prolonged_bear_candles


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
