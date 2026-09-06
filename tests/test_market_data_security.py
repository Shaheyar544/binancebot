"""Tests verifying market data read-only security and absence of execution capabilities."""

from src.exchange.client import BinanceRestClient
from src.exchange.websocket import BinanceWebSocketClient
from src.market_data.pipeline import MarketDataPipeline


def test_market_data_components_have_no_execution_methods() -> None:
    """Market data components must be strictly read-only and have no order execution capability."""
    prohibited_methods = [
        "place_order",
        "cancel_order",
        "modify_order",
        "execute_trade",
        "submit_order",
        "new_order",
        "close_position",
    ]

    for cls in [MarketDataPipeline, BinanceRestClient, BinanceWebSocketClient]:
        for method in prohibited_methods:
            assert not hasattr(cls, method), (
                f"{cls.__name__} must not have execution method '{method}'"
            )


def test_rest_client_only_exposes_read_endpoints() -> None:
    """REST client exposes only read-only market data endpoints."""
    allowed_methods = {
        "get_exchange_info",
        "get_klines",
        "get_premium_index",
        "get_ticker_price",
        "close",
    }
    client_methods = {
        name
        for name in dir(BinanceRestClient)
        if not name.startswith("_") and callable(getattr(BinanceRestClient, name))
    }
    assert client_methods.issubset(allowed_methods)
