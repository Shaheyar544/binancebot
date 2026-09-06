"""Analysis domain models for single-timeframe and multi-timeframe aggregations."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import MarketRegime, Timeframe


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
