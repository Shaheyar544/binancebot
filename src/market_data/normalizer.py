"""Normalizes raw REST and WebSocket market data into immutable domain models."""

from decimal import Decimal
from typing import Any

from src.domain.enums import Timeframe
from src.domain.models import Candle


class CandleNormalizer:
    """Normalizes raw Binance market feeds into validated Candle models."""

    @staticmethod
    def from_rest_raw(symbol: str, timeframe: Timeframe, raw: list[Any]) -> Candle:
        """Convert a raw Binance REST kline array into a Candle model."""
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            open_time=int(raw[0]),
            open=Decimal(str(raw[1])),
            high=Decimal(str(raw[2])),
            low=Decimal(str(raw[3])),
            close=Decimal(str(raw[4])),
            volume=Decimal(str(raw[5])),
            close_time=int(raw[6]),
            is_closed=True,
        )

    @staticmethod
    def from_ws_payload(payload: dict[str, Any]) -> Candle:
        """Convert a raw Binance WebSocket kline event into a Candle model."""
        k = payload.get("k", {})
        timeframe_str = str(k.get("i", "15m"))
        timeframe = Timeframe(timeframe_str)

        return Candle(
            symbol=str(k.get("s", "XAUUSDT")),
            timeframe=timeframe,
            open_time=int(k["t"]),
            open=Decimal(str(k["o"])),
            high=Decimal(str(k["h"])),
            low=Decimal(str(k["l"])),
            close=Decimal(str(k["c"])),
            volume=Decimal(str(k["v"])),
            close_time=int(k["T"]),
            is_closed=bool(k.get("x", False)),
        )
