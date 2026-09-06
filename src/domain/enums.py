"""Core domain enums defining states, regimes, timeframes, and directions."""

from enum import StrEnum


class DecisionState(StrEnum):
    """Required decision states for the XAUUSDT adaptive engine."""

    WAIT = "WAIT"
    BUY = "BUY"
    ADD = "ADD"
    PARTIAL_TP = "PARTIAL_TP"
    EXIT = "EXIT"
    BLOCKED = "BLOCKED"
    NEWS_LOCK = "NEWS_LOCK"
    POST_NEWS_REASSESSMENT = "POST_NEWS_REASSESSMENT"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    RECONCILING = "RECONCILING"
    DATA_UNSAFE = "DATA_UNSAFE"


class MarketRegime(StrEnum):
    """Market regime classification."""

    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    BULLISH_RANGE = "BULLISH_RANGE"
    NEUTRAL = "NEUTRAL"
    BEARISH_RANGE = "BEARISH_RANGE"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    EVENT_RISK = "EVENT_RISK"


class PositionSide(StrEnum):
    """Position direction. Invariant: strictly long-only; SHORT is forbidden."""

    LONG = "LONG"


class OrderSide(StrEnum):
    """Order side: BUY for entries/adds, SELL for TP or exits only."""

    BUY = "BUY"
    SELL = "SELL"


class Timeframe(StrEnum):
    """Trading and analysis timeframes."""

    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class NewsImpact(StrEnum):
    """Macro event and news impact level."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NewsFactLabel(StrEnum):
    """Mandatory classification labels for news/AI intelligence."""

    FACT = "FACT"
    EXPECTATION = "EXPECTATION"
    ANALYSIS = "ANALYSIS"
    AI_INTERPRETATION = "AI_INTERPRETATION"
