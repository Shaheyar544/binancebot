"""Immutable domain models enforcing safety invariants."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.enums import (
    DecisionState,
    MarketRegime,
    OrderSide,
    PositionSide,
    Timeframe,
)


class Candle(BaseModel):
    """Canonical candlestick model. Immutable."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    open_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    close_time: int
    is_closed: bool

    def assert_completed(self) -> None:
        """Verify the candle is completed; incomplete candles must never be used in strategy."""
        if not self.is_closed:
            raise ValueError(
                f"Incomplete candle cannot be used for completed-candle analysis: "
                f"{self.symbol} {self.timeframe} at {self.open_time}"
            )


class OrderIntent(BaseModel):
    """Order submission intent with hard invariant checks. Immutable."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    side: OrderSide
    quantity: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    notional: Decimal = Field(gt=Decimal("0"))
    is_dca: bool = False
    client_order_id: str
    reason: str

    @model_validator(mode="after")
    def validate_dca_cap(self) -> "OrderIntent":
        """Safety Invariant: Every individual DCA order must be <= $500 notional."""
        max_dca_notional = Decimal("500.00")
        if self.is_dca and self.notional > max_dca_notional:
            raise ValueError(
                f"DCA order notional cannot exceed $500: received ${self.notional:.2f}"
            )
        return self


class PositionSnapshot(BaseModel):
    """Immutable snapshot of exchange position state."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    side: PositionSide = PositionSide.LONG
    size: Decimal
    entry_price: Decimal
    leverage: Decimal
    margin: Decimal
    liquidation_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    updated_at: int


class DecisionSnapshot(BaseModel):
    """Immutable audit trail record for every engine decision."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    timestamp: int
    decision_state: DecisionState
    regime: MarketRegime
    indicators: dict[str, Any] = Field(default_factory=dict)
    risk_state: dict[str, Any] = Field(default_factory=dict)
    event_state: dict[str, Any] = Field(default_factory=dict)
    reason: str
    source: str = "Engine"
