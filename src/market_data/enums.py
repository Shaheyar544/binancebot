"""Enums defining price types and market data health states."""

from enum import StrEnum


class PriceType(StrEnum):
    """Classification of market price stream."""

    LAST = "LAST"
    MARK = "MARK"
    INDEX = "INDEX"


class MarketDataHealth(StrEnum):
    """Health and safety states for market data feeds."""

    HEALTHY = "HEALTHY"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    GAP_DETECTED = "GAP_DETECTED"
    INVALID = "INVALID"
    RECOVERING = "RECOVERING"
