"""Tests for market structure, swing points, BOS/CHoCH, and liquidity sweeps."""

from decimal import Decimal

from src.analysis.structure import (
    StructureBreak,
    SwingPoint,
    SwingType,
    detect_liquidity_sweep,
    detect_structure_breaks,
    find_swing_points,
)
from src.domain.enums import Timeframe
from src.domain.models import Candle


def make_candle(idx: int, open_p: str, high_p: str, low_p: str, close_p: str) -> Candle:
    t = 1700000000000 + idx * 900000
    return Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=t,
        open=Decimal(open_p),
        high=Decimal(high_p),
        low=Decimal(low_p),
        close=Decimal(close_p),
        volume=Decimal("100.0"),
        close_time=t + 899999,
        is_closed=True,
    )


def test_find_swing_points() -> None:
    """Detect swing highs and swing lows based on local pivot extrema."""
    # Peak at index 2 (2720), Valley at index 4 (2680)
    candles = [
        make_candle(0, "2700.0", "2705.0", "2695.0", "2702.0"),
        make_candle(1, "2702.0", "2712.0", "2700.0", "2710.0"),
        make_candle(2, "2710.0", "2725.0", "2708.0", "2720.0"),  # Swing high (high=2725)
        make_candle(3, "2715.0", "2718.0", "2700.0", "2705.0"),
        make_candle(4, "2705.0", "2708.0", "2680.0", "2685.0"),  # Swing low (low=2680)
        make_candle(5, "2685.0", "2698.0", "2682.0", "2695.0"),
        make_candle(6, "2695.0", "2705.0", "2690.0", "2700.0"),
    ]
    swings = find_swing_points(candles, window=2)
    highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
    lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

    assert len(highs) >= 1
    assert highs[0].price == Decimal("2725.0")
    assert len(lows) >= 1
    assert lows[0].price == Decimal("2680.0")


def test_detect_bullish_structure_break() -> None:
    """Close above prior swing high detects a bullish Break of Structure (BOS)."""
    swings = [
        SwingPoint(
            index=2,
            timestamp=1700001800000,
            price=Decimal("2720.0"),
            swing_type=SwingType.SWING_HIGH,
        )
    ]
    # Candle closing above 2720
    candles = [
        make_candle(3, "2715.0", "2725.0", "2710.0", "2722.0"),
    ]
    breaks = detect_structure_breaks(candles, swings)
    assert StructureBreak.BULLISH_BOS in breaks


def test_detect_bearish_structure_break() -> None:
    """Close below prior swing low detects a bearish Break of Structure (BOS)."""
    swings = [
        SwingPoint(
            index=2,
            timestamp=1700001800000,
            price=Decimal("2680.0"),
            swing_type=SwingType.SWING_LOW,
        )
    ]
    # Candle closing below 2680
    candles = [
        make_candle(3, "2685.0", "2688.0", "2670.0", "2675.0"),
    ]
    breaks = detect_structure_breaks(candles, swings)
    assert StructureBreak.BEARISH_BOS in breaks


def test_detect_liquidity_sweep() -> None:
    """Wick sweeps beyond swing low but candle closes back inside range."""
    swings = [
        SwingPoint(
            index=1,
            timestamp=1700000900000,
            price=Decimal("2680.0"),
            swing_type=SwingType.SWING_LOW,
        )
    ]
    # Wick dips to 2672 (below 2680), but close is 2684 (above 2680)
    sweep_candle = make_candle(2, "2682.0", "2688.0", "2672.0", "2684.0")
    assert detect_liquidity_sweep(sweep_candle, swings) is True
