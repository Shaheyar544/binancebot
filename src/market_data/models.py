"""Models for price updates and candle continuity gaps."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.domain.enums import Timeframe
from src.market_data.enums import PriceType


class PriceUpdate(BaseModel):
    """Immutable price update with exchange and local timestamps."""

    model_config = ConfigDict(frozen=True)

    symbol: str = "XAUUSDT"
    price_type: PriceType
    price: Decimal = Field(gt=Decimal("0"))
    exchange_timestamp: int
    local_receive_timestamp: int

    @classmethod
    def from_ticker_raw(cls, raw: dict[str, Any], local_receive_time: int) -> "PriceUpdate":
        """Construct from raw Binance ticker/price payload."""
        return cls(
            symbol=str(raw.get("symbol", "XAUUSDT")),
            price_type=PriceType.LAST,
            price=Decimal(str(raw["price"])),
            exchange_timestamp=int(raw.get("time", local_receive_time)),
            local_receive_timestamp=local_receive_time,
        )

    @classmethod
    def from_premium_index_raw(
        cls, raw: dict[str, Any], price_type: PriceType, local_receive_time: int
    ) -> "PriceUpdate":
        """Construct from raw Binance premiumIndex payload."""
        if price_type == PriceType.MARK:
            price_val = Decimal(str(raw["markPrice"]))
        elif price_type == PriceType.INDEX:
            price_val = Decimal(str(raw["indexPrice"]))
        else:
            raise ValueError(f"Unsupported price type for premiumIndex: {price_type}")

        return cls(
            symbol=str(raw.get("symbol", "XAUUSDT")),
            price_type=price_type,
            price=price_val,
            exchange_timestamp=int(raw.get("time", local_receive_time)),
            local_receive_timestamp=local_receive_time,
        )

    def is_stale(self, current_time_ms: int, threshold_ms: int) -> bool:
        """Check if price event exceeds freshness threshold in milliseconds."""
        return (current_time_ms - self.exchange_timestamp) > threshold_ms


class CandleGap(BaseModel):
    """Represents a detected sequence discontinuity in completed candles."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timeframe: Timeframe
    expected_open_time: int
    actual_open_time: int
    detected_at: int
