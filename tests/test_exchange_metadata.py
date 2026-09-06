"""Tests for dynamic Binance exchange metadata parsing and validation."""

from decimal import Decimal

import pytest

from src.exchange.metadata import ExchangeMetadata, SymbolFilters
from tests.fixtures.binance_fixtures import EXCHANGE_INFO_RAW


def test_parse_valid_xauusdt_metadata() -> None:
    """XAUUSDT metadata parses dynamically from exchange info without hardcoding."""
    metadata = ExchangeMetadata.from_raw(EXCHANGE_INFO_RAW)
    filters: SymbolFilters = metadata.get_symbol_filters("XAUUSDT")

    assert filters.symbol == "XAUUSDT"
    assert filters.status == "TRADING"
    assert filters.contract_type == "PERPETUAL"
    assert filters.base_asset == "XAU"
    assert filters.quote_asset == "USDT"
    assert filters.price_precision == 2
    assert filters.quantity_precision == 3

    # Dynamic Decimal filters
    assert filters.tick_size == Decimal("0.01")
    assert filters.min_price == Decimal("100.00")
    assert filters.max_price == Decimal("100000.00")
    assert filters.step_size == Decimal("0.001")
    assert filters.min_qty == Decimal("0.001")
    assert filters.max_qty == Decimal("1000.000")
    assert filters.min_notional == Decimal("5.0")

    assert isinstance(filters.tick_size, Decimal)
    assert isinstance(filters.step_size, Decimal)
    assert isinstance(filters.min_notional, Decimal)


def test_missing_symbol_fails_safely() -> None:
    """Requesting an unsupported symbol must fail safely with a descriptive error."""
    metadata = ExchangeMetadata.from_raw(EXCHANGE_INFO_RAW)
    with pytest.raises(ValueError, match="Symbol 'ETHUSDT' not supported"):
        metadata.get_symbol_filters("ETHUSDT")


def test_inactive_symbol_fails_safely() -> None:
    """Symbol that is not in TRADING state must be rejected."""
    raw_copy = {
        "timezone": "UTC",
        "serverTime": 1700000000000,
        "symbols": [
            {
                "symbol": "XAUUSDT",
                "contractType": "PERPETUAL",
                "status": "BREAK",  # Inactive
                "baseAsset": "XAU",
                "quoteAsset": "USDT",
                "pricePrecision": 2,
                "quantityPrecision": 3,
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": "0.01",
                        "minPrice": "100.0",
                        "maxPrice": "10000.0",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.001",
                        "minQty": "0.001",
                        "maxQty": "1000.0",
                    },
                    {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                ],
            }
        ],
    }
    metadata = ExchangeMetadata.from_raw(raw_copy)
    with pytest.raises(ValueError, match="is not active for trading: status=BREAK"):
        metadata.get_symbol_filters("XAUUSDT")


def test_no_hardcoded_filters_used() -> None:
    """Filters must strictly reflect whatever the exchange provides, e.g. BTCUSDT."""
    metadata = ExchangeMetadata.from_raw(EXCHANGE_INFO_RAW)
    btc_filters = metadata.get_symbol_filters("BTCUSDT")
    assert btc_filters.tick_size == Decimal("0.1")
    assert btc_filters.price_precision == 1
