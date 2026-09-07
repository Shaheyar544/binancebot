"""Strategy entry setup models and detector families."""

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import Candle


class EntryFamily(StrEnum):
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    SUPPORT_RECLAIM = "SUPPORT_RECLAIM"
    TREND_PULLBACK = "TREND_PULLBACK"


class EntrySetup(BaseModel):
    """Identified tactical trade setup."""

    model_config = ConfigDict(frozen=True)

    family: EntryFamily = Field(..., description="Entry pattern family")
    level: Decimal = Field(..., description="Key price level associated with setup")
    stop_loss_ref: Decimal = Field(..., description="Structural reference price for stop loss")


class BreakoutRetestDetector:
    """Detects breakout of key resistance followed by successful retest."""

    def evaluate(
        self,
        candles: Sequence[Candle],
        resistance_level: Decimal,
        atr: Decimal | None = None,
    ) -> EntrySetup | None:
        """Examine recent candles for a confirmed breakout and retest."""
        if len(candles) < 2:
            return None

        breakout_candle = candles[-2]
        retest_candle = candles[-1]

        # Breakout candle must close clearly above resistance
        if breakout_candle.close <= resistance_level:
            return None

        # Retest candle dips into or touches resistance level (low <= resistance)
        # and holds with a bullish close (close > resistance)
        if retest_candle.low <= resistance_level and retest_candle.close > resistance_level:
            candle_ref = min(breakout_candle.low, retest_candle.low)
            if atr is not None and atr > Decimal("0.0"):
                structural_boundary = resistance_level - (Decimal("0.1") * atr)
                stop_ref = min(candle_ref, structural_boundary)
                min_stop_distance = max(Decimal("0.5") * atr, Decimal("0.05"))
                if retest_candle.close - stop_ref < min_stop_distance:
                    return None
            else:
                stop_ref = candle_ref

            return EntrySetup(
                family=EntryFamily.BREAKOUT_RETEST,
                level=resistance_level,
                stop_loss_ref=stop_ref,
            )

        return None


class SupportReclaimDetector:
    """Detects sweep below key support immediately reclaimed with bullish close."""

    def evaluate(
        self,
        candle: Candle,
        support_level: Decimal,
        atr: Decimal | None = None,
    ) -> EntrySetup | None:
        """Examine candle for support sweep and reclaim."""
        # Low pierces beneath support, but close finishes back above support
        if candle.low < support_level and candle.close >= support_level:
            candle_ref = candle.low
            if atr is not None and atr > Decimal("0.0"):
                structural_boundary = support_level - (Decimal("0.1") * atr)
                stop_ref = min(candle_ref, structural_boundary)
                min_stop_distance = max(Decimal("0.5") * atr, Decimal("0.05"))
                if candle.close - stop_ref < min_stop_distance:
                    return None
            else:
                stop_ref = candle_ref

            return EntrySetup(
                family=EntryFamily.SUPPORT_RECLAIM,
                level=support_level,
                stop_loss_ref=stop_ref,
            )

        return None


class TrendPullbackDetector:
    """Detects pullback into dynamic EMA 20/50 support zone in uptrend."""

    def evaluate(
        self,
        candle: Candle,
        ema_20: Decimal,
        ema_50: Decimal,
        atr: Decimal | None = None,
    ) -> EntrySetup | None:
        """Examine candle for pullback into EMA zone with bullish reaction."""
        # Valid EMA zone in uptrend: ema_20 > ema_50
        upper_zone = max(ema_20, ema_50)
        lower_zone = min(ema_20, ema_50)

        # Candle dips into the EMA support zone
        if candle.low <= upper_zone and candle.low >= lower_zone:
            # Bullish reaction: candle closes above the zone or closes bullishly
            reaction_ok = candle.close > candle.open or candle.close > upper_zone
            if candle.close >= lower_zone and reaction_ok:
                candle_ref = candle.low
                if atr is not None and atr > Decimal("0.0"):
                    structural_boundary = lower_zone - (Decimal("0.1") * atr)
                    stop_ref = min(candle_ref, structural_boundary)
                    min_stop_distance = max(Decimal("0.5") * atr, Decimal("0.05"))
                    if candle.close - stop_ref < min_stop_distance:
                        return None
                else:
                    stop_ref = candle_ref

                return EntrySetup(
                    family=EntryFamily.TREND_PULLBACK,
                    level=upper_zone,
                    stop_loss_ref=stop_ref,
                )

        return None


class EntryOrchestrator:
    """Orchestrates dynamic support/resistance level identification and tactical entry detectors."""

    def __init__(self) -> None:
        self.breakout_detector = BreakoutRetestDetector()
        self.reclaim_detector = SupportReclaimDetector()
        self.pullback_detector = TrendPullbackDetector()

    def identify_levels(
        self,
        candles: Sequence[Candle],
        window: int = 2,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Derive latest valid swing support and swing resistance levels from candle history."""
        from src.analysis.structure import SwingType, find_swing_points

        swings = find_swing_points(candles, window=window)
        highs = [s for s in swings if s.swing_type == SwingType.SWING_HIGH]
        lows = [s for s in swings if s.swing_type == SwingType.SWING_LOW]

        recent_resistance = highs[-1].price if highs else None
        recent_support = lows[-1].price if lows else None
        return recent_support, recent_resistance

    def evaluate_setups(
        self,
        candles_15m: Sequence[Candle],
        ema_20: Decimal,
        ema_50: Decimal,
        support_level: Decimal | None = None,
        resistance_level: Decimal | None = None,
        atr: Decimal | None = None,
    ) -> EntrySetup | None:
        """Evaluate all candidate entry families against latest 15M candles and derived levels."""
        if not candles_15m:
            return None

        latest_candle = candles_15m[-1]

        # 1. Check Breakout-Retest if resistance level is available
        if resistance_level is not None and len(candles_15m) >= 2:
            setup = self.breakout_detector.evaluate(candles_15m, resistance_level, atr=atr)
            if setup is not None:
                return setup

        # 2. Check Support Reclaim if support level is available
        if support_level is not None:
            setup = self.reclaim_detector.evaluate(latest_candle, support_level, atr=atr)
            if setup is not None:
                return setup

        # 3. Check Trend Pullback into EMA 20/50
        setup = self.pullback_detector.evaluate(latest_candle, ema_20, ema_50, atr=atr)
        if setup is not None:
            return setup

        return None
