"""Analysis domain models for single-timeframe and multi-timeframe aggregations."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import MarketRegime, Timeframe
from src.domain.models import Candle


class TimeframeAnalysis(BaseModel):
    """Immutable summary of indicator and structural analysis on a single timeframe."""

    model_config = ConfigDict(frozen=True)

    timeframe: Timeframe = Field(..., description="Timeframe of analysis")
    is_bullish: bool = Field(..., description="Overall bullish structure/bias on this timeframe")
    current_close: Decimal = Field(..., description="Latest closed candle price")
    ema_10: Decimal = Field(..., description="10-period EMA")
    ema_20: Decimal = Field(..., description="20-period EMA")
    ema_50: Decimal = Field(..., description="50-period EMA")
    ema_200: Decimal = Field(..., description="200-period EMA")
    rsi: Decimal = Field(..., description="14-period RSI")
    atr: Decimal = Field(..., description="14-period ATR")
    volume_ratio: Decimal = Field(..., description="Ratio of latest volume to average volume")


class MultiTimeframeAnalysis(BaseModel):
    """Immutable cross-timeframe aggregated analysis across 1D, 4H, 1H, and 15M."""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(..., description="Trading pair symbol e.g. XAUUSDT")
    regime: MarketRegime = Field(..., description="Overall market regime classification")
    analysis_1d: TimeframeAnalysis = Field(..., description="1D macro timeframe analysis")
    analysis_4h: TimeframeAnalysis = Field(..., description="4H intermediate structural analysis")
    analysis_1h: TimeframeAnalysis = Field(..., description="1H trend confirmation analysis")
    analysis_15m: TimeframeAnalysis = Field(..., description="15M tactical entry setup analysis")
    timestamp: int = Field(
        ..., ge=0, description="Timestamp of the analysis snapshot in milliseconds"
    )


class TimeframeAnalyzer:
    """Derives deterministic technical indicators, structure, and bullish bias."""

    @staticmethod
    def is_bullish_structure(
        candles: list[Candle],
        timeframe: Timeframe,
        swing_window: int | None = None,
    ) -> bool:
        """Determine if a timeframe possesses bullish market structure."""
        from src.analysis.indicators import calculate_ema
        from src.analysis.structure import (
            DEFAULT_SWING_WINDOWS,
            StructureBreak,
            detect_structure_breaks,
            find_swing_points,
        )

        if not candles:
            return False

        window = swing_window or DEFAULT_SWING_WINDOWS.get(timeframe.value, 2)
        swings = find_swing_points(candles, window=window)
        breaks = detect_structure_breaks(candles, swings)

        # Immediate structure breaks
        if (
            StructureBreak.BEARISH_TO_BULLISH_CHOCH in breaks
            or StructureBreak.BULLISH_BOS in breaks
        ):
            return True
        if (
            StructureBreak.BULLISH_TO_BEARISH_CHOCH in breaks
            or StructureBreak.BEARISH_BOS in breaks
        ):
            return False

        # Evaluate swing sequence
        highs = [s for s in swings if s.swing_type.value == "SWING_HIGH"]
        lows = [s for s in swings if s.swing_type.value == "SWING_LOW"]

        if len(highs) >= 2 and len(lows) >= 2:
            is_hh = highs[-1].price > highs[-2].price
            is_hl = lows[-1].price > lows[-2].price
            if is_hh and is_hl:
                return True
            if not is_hh and not is_hl:
                return False

        # Fallback to moving averages
        closes = [c.close for c in candles]
        if len(closes) >= 50:
            ema_50 = calculate_ema(closes, 50)
            return closes[-1] > ema_50
        elif len(closes) >= 20:
            ema_20 = calculate_ema(closes, 20)
            return closes[-1] > ema_20
        elif len(closes) >= 2:
            return closes[-1] > closes[0]

        return False

    @classmethod
    def analyze_timeframe(
        cls,
        candles: list[Candle],
        timeframe: Timeframe,
        swing_window: int | None = None,
    ) -> TimeframeAnalysis:
        """Derive complete TimeframeAnalysis from a completed candle sequence."""
        from src.analysis.indicators import (
            calculate_atr,
            calculate_ema,
            calculate_rsi,
            calculate_volume_ratio,
        )

        if not candles:
            raise ValueError(f"Cannot analyze empty candle series for {timeframe.value}")

        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]
        latest_close = closes[-1]

        ema_10 = calculate_ema(closes, 10) if len(closes) >= 10 else latest_close
        ema_20 = calculate_ema(closes, 20) if len(closes) >= 20 else ema_10
        ema_50 = calculate_ema(closes, 50) if len(closes) >= 50 else ema_20
        ema_200 = calculate_ema(closes, 200) if len(closes) >= 200 else ema_50

        rsi = calculate_rsi(closes, period=14) if len(closes) >= 15 else Decimal("50.0")
        atr = calculate_atr(candles, period=14) if len(candles) >= 14 else Decimal("10.0")
        volume_ratio = (
            calculate_volume_ratio(volumes, period=20) if len(volumes) >= 20 else Decimal("1.0")
        )

        is_bullish = cls.is_bullish_structure(candles, timeframe, swing_window=swing_window)

        return TimeframeAnalysis(
            timeframe=timeframe,
            is_bullish=is_bullish,
            current_close=latest_close,
            ema_10=ema_10,
            ema_20=ema_20,
            ema_50=ema_50,
            ema_200=ema_200,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
        )

    @classmethod
    def build_multi_timeframe_analysis(
        cls,
        symbol: str,
        candles_1d: list[Candle],
        candles_4h: list[Candle],
        candles_1h: list[Candle],
        candles_15m: list[Candle],
        regime_classifier: object | None = None,
        event_risk_active: bool = False,
    ) -> MultiTimeframeAnalysis:
        """Build canonical MultiTimeframeAnalysis across 1D, 4H, 1H, and 15M."""
        from src.analysis.regime import RegimeClassifier

        analysis_1d = cls.analyze_timeframe(candles_1d, Timeframe.D1)
        analysis_4h = cls.analyze_timeframe(candles_4h, Timeframe.H4)
        analysis_1h = cls.analyze_timeframe(candles_1h, Timeframe.H1)
        analysis_15m = cls.analyze_timeframe(candles_15m, Timeframe.M15)

        if event_risk_active:
            regime = MarketRegime.EVENT_RISK
        else:
            classifier: RegimeClassifier = (
                regime_classifier
                if isinstance(regime_classifier, RegimeClassifier)
                else RegimeClassifier()
            )
            regime = classifier.classify(
                ema_10=analysis_15m.ema_10,
                ema_20=analysis_15m.ema_20,
                ema_50=analysis_15m.ema_50,
                ema_200=analysis_15m.ema_200,
                current_close=analysis_15m.current_close,
                atr=analysis_15m.atr,
                avg_atr=analysis_15m.atr,
                is_bullish_structure=analysis_15m.is_bullish,
            )

        timestamp = candles_15m[-1].close_time if candles_15m else 0

        return MultiTimeframeAnalysis(
            symbol=symbol,
            regime=regime,
            analysis_1d=analysis_1d,
            analysis_4h=analysis_4h,
            analysis_1h=analysis_1h,
            analysis_15m=analysis_15m,
            timestamp=timestamp,
        )
