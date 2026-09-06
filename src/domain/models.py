"""Immutable domain models enforcing safety invariants and precise financial semantics."""

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

MAX_DCA_NOTIONAL = Decimal("500")


class Candle(BaseModel):
    """Canonical candlestick model. Immutable with OHLC validation."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    timeframe: Timeframe
    open_time: int
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: Decimal = Field(ge=Decimal("0"))
    close_time: int
    is_closed: bool

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        """Reject mathematically impossible OHLC relationships."""
        if self.high < self.low:
            raise ValueError(
                f"high must be greater than or equal to low: high={self.high}, low={self.low}"
            )
        if self.high < self.open:
            raise ValueError(f"high cannot be less than open: high={self.high}, open={self.open}")
        if self.high < self.close:
            raise ValueError(
                f"high cannot be less than close: high={self.high}, close={self.close}"
            )
        if self.low > self.open:
            raise ValueError(f"low cannot be greater than open: low={self.low}, open={self.open}")
        if self.low > self.close:
            raise ValueError(
                f"low cannot be greater than close: low={self.low}, close={self.close}"
            )
        if self.close_time <= self.open_time:
            raise ValueError(
                "close_time must be greater than open_time: "
                f"open={self.open_time}, close={self.close_time}"
            )
        return self

    def assert_completed(self) -> None:
        """Verify the candle is completed; incomplete candles must never be used in strategy."""
        if not self.is_closed:
            raise ValueError(
                f"Incomplete candle cannot be used for completed-candle analysis: "
                f"{self.symbol} {self.timeframe} at {self.open_time}"
            )


class MarketSnapshot(BaseModel):
    """Canonical, immutable representation of current market state."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    timestamp: int
    last_price: Decimal = Field(gt=Decimal("0"))
    mark_price: Decimal = Field(gt=Decimal("0"))
    index_price: Decimal = Field(gt=Decimal("0"))
    funding_rate: Decimal = Decimal("0")
    candles: dict[Timeframe, Candle] = Field(default_factory=dict)


class OrderIntent(BaseModel):
    """Order submission intent with hard invariant checks. Immutable."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    side: OrderSide
    order_type: str = "LIMIT"
    quantity: Decimal = Field(gt=Decimal("0"))
    price: Decimal = Field(gt=Decimal("0"))
    notional: Decimal = Field(gt=Decimal("0"))
    is_dca: bool = False
    is_opening: bool = True
    client_order_id: str
    reason: str

    @model_validator(mode="after")
    def validate_invariants(self) -> "OrderIntent":
        """Enforce DCA notional limit and long-only side semantics."""
        # 1. DCA hard limit ($500 max)
        if self.is_dca and self.notional > MAX_DCA_NOTIONAL:
            raise ValueError(
                f"DCA order notional cannot exceed $500: received ${self.notional:.2f}"
            )

        # 2. Long-only side validation
        if self.is_opening and self.side != OrderSide.BUY:
            raise ValueError("Opening orders must use BUY; short positions are strictly forbidden")
        if not self.is_opening and self.side != OrderSide.SELL:
            raise ValueError("Closing orders must use SELL; buy orders cannot close positions")

        return self


class PositionSnapshot(BaseModel):
    """Immutable snapshot of exchange position state. Strictly long-only."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    side: PositionSide = PositionSide.LONG
    size: Decimal = Field(gt=Decimal("0"))
    entry_price: Decimal = Field(gt=Decimal("0"))
    leverage: Decimal = Field(ge=Decimal("1.0"))
    margin: Decimal = Field(gt=Decimal("0"))
    liquidation_price: Decimal = Field(gt=Decimal("0"))
    unrealized_pnl: Decimal = Decimal("0")
    updated_at: int = 0


class DecisionSnapshot(BaseModel):
    """Immutable audit trail record for every engine decision."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    symbol: str = "XAUUSDT"
    timestamp: int
    decision_state: DecisionState
    regime: MarketRegime
    reason: str
    indicators: dict[str, Any] = Field(default_factory=dict)
    risk_state: dict[str, Any] = Field(default_factory=dict)
    event_state: dict[str, Any] = Field(default_factory=dict)
    source: str = "Engine"
