"""Tests for Phase 4A: Dynamic Structural Stop & Risk Geometry Remediation."""

from decimal import Decimal

from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.strategy.entry_families import (
    BreakoutRetestDetector,
    EntryFamily,
    EntryOrchestrator,
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


def test_trend_pullback_relocates_stop_to_structural_ema_boundary() -> None:
    """Pullback candle low may be tight, but structural invalidation lies below EMA 50."""
    detector = TrendPullbackDetector()
    ema_20 = Decimal("2710.0")
    ema_50 = Decimal("2700.0")
    atr = Decimal("6.0")  # 0.5 * atr = 3.0, 0.1 * atr = 0.6

    # Candle dips to 2708.0 and closes at 2714.0
    # Old stop = 2708.0 (R = 6.0)
    # Structural stop = min(candle.low, ema_50 - 0.1*atr) = min(2708.0, 2700.0 - 0.6) = 2699.4
    # Remediated R = 2714.0 - 2699.4 = 14.6
    candle = make_candle(0, "2716.0", "2718.0", "2708.0", "2714.0")
    setup = detector.evaluate(candle, ema_20=ema_20, ema_50=ema_50, atr=atr)
    assert setup is not None
    assert setup.family == EntryFamily.TREND_PULLBACK
    assert setup.stop_loss_ref == Decimal("2699.4")
    assert (candle.close - setup.stop_loss_ref) >= Decimal("0.5") * atr


def test_micro_stop_rejected_by_dynamic_volatility_noise_floor() -> None:
    """If stop distance cannot exceed 0.5 * ATR, setup is rejected as inside market noise."""
    detector = TrendPullbackDetector()
    ema_20 = Decimal("2710.0")
    ema_50 = Decimal("2709.9")
    atr = Decimal("6.0")  # 0.5 * atr = 3.0

    # Candle low is 2709.95, close is 2710.00
    # Even with structural boundary, if R < 0.5 * ATR (3.0), it must be rejected
    candle = make_candle(0, "2710.0", "2710.5", "2709.95", "2710.0")
    # Structural boundary ema_50 - 0.1*atr = 2709.9 - 0.6 = 2709.3 -> R = 0.70 < 3.0
    setup = detector.evaluate(candle, ema_20=ema_20, ema_50=ema_50, atr=atr)
    assert setup is None


def test_support_reclaim_relocates_stop_below_swept_support() -> None:
    """Support reclaim stop is placed below swept support level with buffer."""
    detector = SupportReclaimDetector()
    support_level = Decimal("2690.0")
    atr = Decimal("5.0")  # buffer = 0.5, noise floor = 2.5

    # Candle sweeps below 2690 to 2689.8 (tight sweep), closes at 2695.0
    # Old stop = 2689.8
    # Structural stop = min(2689.8, 2690.0 - 0.5) = 2689.5
    candle = make_candle(0, "2692.0", "2696.0", "2689.8", "2695.0")
    setup = detector.evaluate(candle, support_level=support_level, atr=atr)
    assert setup is not None
    assert setup.family == EntryFamily.SUPPORT_RECLAIM
    assert setup.stop_loss_ref == Decimal("2689.5")
    assert (candle.close - setup.stop_loss_ref) >= Decimal("2.5")


def test_breakout_retest_relocates_stop_below_retested_level() -> None:
    """Breakout retest stop is placed below resistance level with buffer."""
    detector = BreakoutRetestDetector()
    resistance_level = Decimal("2720.0")
    atr = Decimal("4.0")  # buffer = 0.4, noise floor = 2.0

    # Candle 0 breaks out above 2720
    # Candle 1 touches 2720 (low=2720.0), closes at 2725.0
    # Old stop = 2714.0 (breakout low)
    # Structural stop = min(breakout.low, retest.low, resistance - 0.4) = 2714.0
    candles = [
        make_candle(0, "2715.0", "2728.0", "2714.0", "2725.0"),
        make_candle(1, "2725.0", "2728.0", "2720.0", "2726.0"),
    ]
    setup = detector.evaluate(candles, resistance_level=resistance_level, atr=atr)
    assert setup is not None
    assert setup.family == EntryFamily.BREAKOUT_RETEST
    assert setup.stop_loss_ref == Decimal("2714.0")
    assert (candles[-1].close - setup.stop_loss_ref) >= Decimal("2.0")


def test_orchestrator_passes_atr_and_rejects_sub_noise_setups() -> None:
    """EntryOrchestrator rejects tactical setup if stop is tighter than dynamic noise floor."""
    orchestrator = EntryOrchestrator()
    pullback_candle = make_candle(0, "2710.0", "2711.0", "2709.8", "2710.0")
    # High ATR makes 0.5 * ATR = 5.0
    setup = orchestrator.evaluate_setups(
        candles_15m=[pullback_candle],
        ema_20=Decimal("2710.0"),
        ema_50=Decimal("2709.5"),
        atr=Decimal("10.0"),
    )
    assert setup is None
