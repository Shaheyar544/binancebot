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
            return EntrySetup(
                family=EntryFamily.BREAKOUT_RETEST,
                level=resistance_level,
                stop_loss_ref=min(breakout_candle.low, retest_candle.low),
            )

        return None


class SupportReclaimDetector:
    """Detects sweep below key support immediately reclaimed with bullish close."""

    def evaluate(
        self,
        candle: Candle,
        support_level: Decimal,
    ) -> EntrySetup | None:
        """Examine candle for support sweep and reclaim."""
        # Low pierces beneath support, but close finishes back above support
        if candle.low < support_level and candle.close >= support_level:
            return EntrySetup(
                family=EntryFamily.SUPPORT_RECLAIM,
                level=support_level,
                stop_loss_ref=candle.low,
            )

        return None


class TrendPullbackDetector:
    """Detects pullback into dynamic EMA 20/50 support zone in uptrend."""

    def evaluate(
        self,
        candle: Candle,
        ema_20: Decimal,
        ema_50: Decimal,
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
                return EntrySetup(
                    family=EntryFamily.TREND_PULLBACK,
                    level=upper_zone,
                    stop_loss_ref=candle.low,
                )

        return None
