"""Dynamic Binance exchange metadata and symbol filter representation."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SymbolFilters(BaseModel):
    """Dynamic trading filters for a Binance contract. Immutable."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    status: str
    contract_type: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int

    # Dynamic Decimal filters
    tick_size: Decimal = Field(gt=Decimal("0"))
    min_price: Decimal = Field(gt=Decimal("0"))
    max_price: Decimal = Field(gt=Decimal("0"))

    step_size: Decimal = Field(gt=Decimal("0"))
    min_qty: Decimal = Field(gt=Decimal("0"))
    max_qty: Decimal = Field(gt=Decimal("0"))

    min_notional: Decimal = Field(gt=Decimal("0"))

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SymbolFilters":
        """Parse raw Binance symbol definition dynamically without hardcoding."""
        filters_by_type: dict[str, dict[str, Any]] = {
            f.get("filterType", ""): f for f in raw.get("filters", [])
        }

        price_filter = filters_by_type.get("PRICE_FILTER", {})
        lot_filter = filters_by_type.get("LOT_SIZE", {})
        notional_filter = filters_by_type.get("MIN_NOTIONAL", {})

        return cls(
            symbol=str(raw.get("symbol", "")),
            status=str(raw.get("status", "")),
            contract_type=str(raw.get("contractType", "")),
            base_asset=str(raw.get("baseAsset", "")),
            quote_asset=str(raw.get("quoteAsset", "")),
            price_precision=int(raw.get("pricePrecision", 2)),
            quantity_precision=int(raw.get("quantityPrecision", 3)),
            tick_size=Decimal(str(price_filter.get("tickSize", "0.01"))),
            min_price=Decimal(str(price_filter.get("minPrice", "0.01"))),
            max_price=Decimal(str(price_filter.get("maxPrice", "1000000.00"))),
            step_size=Decimal(str(lot_filter.get("stepSize", "0.001"))),
            min_qty=Decimal(str(lot_filter.get("minQty", "0.001"))),
            max_qty=Decimal(str(lot_filter.get("maxQty", "10000.000"))),
            min_notional=Decimal(str(notional_filter.get("notional", "5.0"))),
        )


class ExchangeMetadata(BaseModel):
    """Dynamic exchange metadata holding all symbol filters."""

    model_config = ConfigDict(frozen=True)

    timezone: str
    server_time: int
    symbols: dict[str, SymbolFilters]

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ExchangeMetadata":
        """Build metadata container from raw exchangeInfo payload."""
        symbols_map: dict[str, SymbolFilters] = {}
        for s in raw.get("symbols", []):
            filters = SymbolFilters.from_raw(s)
            symbols_map[filters.symbol] = filters

        return cls(
            timezone=str(raw.get("timezone", "UTC")),
            server_time=int(raw.get("serverTime", 0)),
            symbols=symbols_map,
        )

    def get_symbol_filters(self, symbol: str) -> SymbolFilters:
        """Retrieve and validate symbol filters dynamically. Fails safely if missing/inactive."""
        if symbol not in self.symbols:
            raise ValueError(f"Symbol '{symbol}' not supported by exchange metadata")

        filters = self.symbols[symbol]
        if filters.status != "TRADING":
            raise ValueError(
                f"Symbol '{symbol}' is not active for trading: status={filters.status}"
            )

        return filters
