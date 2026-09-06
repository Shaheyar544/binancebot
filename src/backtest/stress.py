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


def generate_v_recovery_candles(
    start_price: Decimal,
    drop_pct: Decimal = Decimal("0.05"),
    num_candles_down: int = 6,
    num_candles_up: int = 6,
) -> list[Candle]:
    """Generate synthetic sequence modeling a sharp drop followed by swift V-recovery."""
    candles: list[Candle] = []
    base_time = 1700000000000
    interval_ms = 900000
    current_p = start_price
    trough_price = start_price * (Decimal("1.0") - drop_pct)
    down_step = (start_price - trough_price) / Decimal(str(num_candles_down))
    up_step = (start_price - trough_price) / Decimal(str(num_candles_up))

    idx = 0
    # Downward leg
    for _ in range(num_candles_down):
        open_p = current_p
        close_p = current_p - down_step
        high_p = open_p + Decimal("1.0")
        low_p = close_p - Decimal("1.0")
        candles.append(
            Candle(
                symbol="XAUUSDT",
                timeframe=Timeframe.M15,
                open_time=base_time + idx * interval_ms,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("300.0"),
                close_time=base_time + (idx + 1) * interval_ms - 1,
                is_closed=True,
            )
        )
        current_p = close_p
        idx += 1

    # Upward recovery leg
    for _ in range(num_candles_up):
        open_p = current_p
        close_p = current_p + up_step
        high_p = close_p + Decimal("1.0")
        low_p = open_p - Decimal("1.0")
        candles.append(
            Candle(
                symbol="XAUUSDT",
                timeframe=Timeframe.M15,
                open_time=base_time + idx * interval_ms,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("600.0"),
                close_time=base_time + (idx + 1) * interval_ms - 1,
                is_closed=True,
            )
        )
        current_p = close_p
        idx += 1

    return candles


def generate_sideways_candles(
    mid_price: Decimal,
    amplitude: Decimal = Decimal("5.0"),
    num_candles: int = 20,
) -> list[Candle]:
    """Generate synthetic range-bound sideways sequence oscillating around mid_price."""
    candles: list[Candle] = []
    base_time = 1700000000000
    interval_ms = 900000

    for i in range(num_candles):
        offset = amplitude if i % 2 == 0 else -amplitude
        open_p = mid_price - (offset / Decimal("2.0"))
        close_p = mid_price + offset
        high_p = max(open_p, close_p) + Decimal("2.0")
        low_p = min(open_p, close_p) - Decimal("2.0")

        candles.append(
            Candle(
                symbol="XAUUSDT",
                timeframe=Timeframe.M15,
                open_time=base_time + i * interval_ms,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("100.0"),
                close_time=base_time + (i + 1) * interval_ms - 1,
                is_closed=True,
            )
        )

    return candles


def generate_bull_trend_candles(
    start_price: Decimal,
    num_candles: int = 25,
    step: Decimal = Decimal("4.0"),
) -> list[Candle]:
    """Generate synthetic sequence modeling a steady bullish uptrend."""
    candles: list[Candle] = []
    base_time = 1700000000000
    interval_ms = 900000
    current_p = start_price

    for i in range(num_candles):
        open_p = current_p
        close_p = current_p + step
        high_p = close_p + Decimal("2.0")
        low_p = open_p - Decimal("1.0")

        candles.append(
            Candle(
                symbol="XAUUSDT",
                timeframe=Timeframe.M15,
                open_time=base_time + i * interval_ms,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("250.0"),
                close_time=base_time + (i + 1) * interval_ms - 1,
                is_closed=True,
            )
        )
        current_p = close_p

    return candles


def generate_extreme_volatility_candles(
    mid_price: Decimal,
    num_candles: int = 20,
    swing_amplitude: Decimal = Decimal("25.0"),
) -> list[Candle]:
    """Generate synthetic sequence with erratic high-volatility wicks."""
    candles: list[Candle] = []
    base_time = 1700000000000
    interval_ms = 900000

    for i in range(num_candles):
        direction = Decimal("1.0") if i % 2 == 0 else Decimal("-1.0")
        open_p = mid_price
        close_p = mid_price + (Decimal("5.0") * direction)
        high_p = mid_price + swing_amplitude
        low_p = mid_price - swing_amplitude

        candles.append(
            Candle(
                symbol="XAUUSDT",
                timeframe=Timeframe.M15,
                open_time=base_time + i * interval_ms,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal("800.0"),
                close_time=base_time + (i + 1) * interval_ms - 1,
                is_closed=True,
            )
        )

    return candles
