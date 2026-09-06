"""Market structure analysis, swing points, structure breaks, and liquidity sweeps."""

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import Candle


class SwingType(StrEnum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"


class StructureBreak(StrEnum):
    BULLISH_BOS = "BULLISH_BOS"
    BEARISH_BOS = "BEARISH_BOS"
    CHOCH = "CHOCH"


class SwingPoint(BaseModel):
    """Identified swing high or swing low pivot point."""

    model_config = ConfigDict(frozen=True)

    index: int = Field(..., ge=0, description="Bar index in the sequence")
    timestamp: int = Field(..., ge=0, description="Candle open timestamp in milliseconds")
    price: Decimal = Field(..., description="Pivot price level")
    swing_type: SwingType = Field(..., description="Swing high or swing low")


def find_swing_points(candles: Sequence[Candle], window: int = 2) -> list[SwingPoint]:
    """Identify local swing highs and swing lows using a symmetric rolling window."""
    if len(candles) < 2 * window + 1:
        return []

    swings: list[SwingPoint] = []
    n = len(candles)

    for i in range(window, n - window):
        c = candles[i]
        # Check swing high
        is_high = True
        for offset in range(1, window + 1):
            if candles[i - offset].high >= c.high or candles[i + offset].high > c.high:
                is_high = False
                break
        if is_high:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=c.open_time,
                    price=c.high,
                    swing_type=SwingType.SWING_HIGH,
                )
            )

        # Check swing low
        is_low = True
        for offset in range(1, window + 1):
            if candles[i - offset].low <= c.low or candles[i + offset].low < c.low:
                is_low = False
                break
        if is_low:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=c.open_time,
                    price=c.low,
                    swing_type=SwingType.SWING_LOW,
                )
            )

    return swings


def detect_structure_breaks(
    candles: Sequence[Candle],
    swings: Sequence[SwingPoint],
) -> list[StructureBreak]:
    """Detect Break of Structure (BOS) or Change of Character (CHoCH)."""
    breaks: list[StructureBreak] = []
    if not candles or not swings:
        return breaks

    recent_highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
    recent_lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

    latest_candle = candles[-1]

    if recent_highs:
        last_high = recent_highs[-1]
        if latest_candle.close > last_high.price:
            breaks.append(StructureBreak.BULLISH_BOS)

    if recent_lows:
        last_low = recent_lows[-1]
        if latest_candle.close < last_low.price:
            breaks.append(StructureBreak.BEARISH_BOS)

    return breaks


def detect_liquidity_sweep(candle: Candle, swings: Sequence[SwingPoint]) -> bool:
    """Detect if candle wick penetrated a swing low but closed back inside/above it."""
    recent_lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]
    if not recent_lows:
        return False

    last_low = recent_lows[-1]
    if candle.low < last_low.price and candle.close >= last_low.price:
        return True

    return False
