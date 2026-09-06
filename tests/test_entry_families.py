"""Tests for strategy entry setup families: Breakout-Retest, Support Reclaim, and Trend Pullback."""

from decimal import Decimal

from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.strategy.entry_families import (
    BreakoutRetestDetector,
    EntryFamily,
    SupportReclaimDetector,
    TrendPullbackDetector,
)


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


def test_breakout_retest_detection() -> None:
    """Resistance level broken then retested with a bullish close."""
    detector = BreakoutRetestDetector()
    resistance_level = Decimal("2720.0")

    # Candle 0: breaks above 2720, closes 2725
    # Candle 1: dips to test 2720 (low=2719.5), closes bullish at 2726
    candles = [
        make_candle(0, "2715.0", "2728.0", "2714.0", "2725.0"),
        make_candle(1, "2725.0", "2728.0", "2719.5", "2726.0"),
    ]
    setup = detector.evaluate(candles, resistance_level)
    assert setup is not None
    assert setup.family == EntryFamily.BREAKOUT_RETEST
    assert setup.level == resistance_level


def test_support_reclaim_detection() -> None:
    """Support level swept and reclaimed immediately with bullish close."""
    detector = SupportReclaimDetector()
    support_level = Decimal("2690.0")

    # Candle sweeps below 2690 (low=2684), but closes back above at 2694
    candle = make_candle(0, "2692.0", "2696.0", "2684.0", "2694.0")
    setup = detector.evaluate(candle, support_level)
    assert setup is not None
    assert setup.family == EntryFamily.SUPPORT_RECLAIM


def test_trend_pullback_detection() -> None:
    """Price pulls back into EMA 20/50 zone in uptrend and bounces."""
    detector = TrendPullbackDetector()
    ema_20 = Decimal("2710.0")
    ema_50 = Decimal("2700.0")

    # Pullback candle tags 2708 (between 2700 and 2710) and closes strong at 2714
    candle = make_candle(0, "2716.0", "2718.0", "2708.0", "2714.0")
    setup = detector.evaluate(candle, ema_20=ema_20, ema_50=ema_50)
    assert setup is not None
    assert setup.family == EntryFamily.TREND_PULLBACK


def test_entry_orchestrator_dynamic_levels() -> None:
    """EntryOrchestrator dynamically derives levels and identifies tactical setup."""
    from src.strategy.entry_families import EntryOrchestrator

    orchestrator = EntryOrchestrator()
    # Highs at 2730, lows at 2690
    candles = [
        make_candle(0, "2700.0", "2710.0", "2690.0", "2705.0"),
        make_candle(1, "2705.0", "2730.0", "2700.0", "2725.0"),
        make_candle(2, "2725.0", "2728.0", "2715.0", "2720.0"),
        make_candle(3, "2720.0", "2722.0", "2705.0", "2710.0"),
        make_candle(4, "2710.0", "2715.0", "2700.0", "2705.0"),
    ]
    support, resistance = orchestrator.identify_levels(candles, window=1)
    assert support is not None or resistance is not None

    # Trend pullback setup evaluation
    pullback_candle = make_candle(5, "2716.0", "2718.0", "2708.0", "2714.0")
    setup = orchestrator.evaluate_setups(
        candles_15m=[pullback_candle],
        ema_20=Decimal("2710.0"),
        ema_50=Decimal("2700.0"),
    )
    assert setup is not None
    assert setup.family == EntryFamily.TREND_PULLBACK
