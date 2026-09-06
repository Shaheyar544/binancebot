"""Stress testing fixtures and synthetic shock scenario generators."""

from decimal import Decimal

from src.domain.enums import Timeframe
from src.domain.models import Candle


def generate_flash_crash_candles(
    start_price: Decimal,
    drop_pct: Decimal,
    num_candles: int = 8,
) -> list[Candle]:
    """Generate synthetic sequence modeling a sharp flash crash."""
    candles: list[Candle] = []
    current_p = start_price
    step_drop = (start_price * drop_pct) / Decimal(str(num_candles))

    base_time = 1700000000000
    interval_ms = 900000  # 15M

    for i in range(num_candles):
        open_p = current_p
        close_p = current_p - step_drop
        high_p = open_p + Decimal("1.0")
        low_p = close_p - Decimal("1.0")

        c = Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=base_time + i * interval_ms,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            volume=Decimal("500.0"),
            close_time=base_time + (i + 1) * interval_ms - 1,
            is_closed=True,
        )
        candles.append(c)
        current_p = close_p

    return candles


def generate_prolonged_bear_candles(
    start_price: Decimal,
    num_candles: int = 20,
) -> list[Candle]:
    """Generate synthetic sequence modeling a sustained downtrend."""
    candles: list[Candle] = []
    current_p = start_price
    step = Decimal("5.0")
    base_time = 1700000000000
    interval_ms = 900000

    for i in range(num_candles):
        open_p = current_p
        close_p = current_p - step
        high_p = open_p + Decimal("2.0")
        low_p = close_p - Decimal("2.0")

        c = Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=base_time + i * interval_ms,
            open=open_p,
            high=high_p,
            low=low_p,
            close=close_p,
            volume=Decimal("150.0"),
            close_time=base_time + (i + 1) * interval_ms - 1,
            is_closed=True,
        )
        candles.append(c)
        current_p = close_p

    return candles
