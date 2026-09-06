"""Tests for BinanceRestClient using deterministic httpx.MockTransport."""

import httpx
import pytest

from src.exchange.client import BinanceRestClient
from tests.fixtures.binance_fixtures import (
    EXCHANGE_INFO_RAW,
    KLINES_RAW_15M,
    PREMIUM_INDEX_RAW,
    TICKER_PRICE_RAW,
)


@pytest.mark.asyncio
async def test_rest_client_endpoints_success() -> None:
    """REST client methods return parsed JSON payloads from mock transport."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "exchangeInfo" in path:
            return httpx.Response(200, json=EXCHANGE_INFO_RAW)
        if "klines" in path:
            return httpx.Response(200, json=KLINES_RAW_15M)
        if "premiumIndex" in path:
            return httpx.Response(200, json=PREMIUM_INDEX_RAW)
        if "ticker/price" in path:
            return httpx.Response(200, json=TICKER_PRICE_RAW)
        return httpx.Response(404)

    transport = httpx.MockTransport(mock_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = BinanceRestClient(http_client=http_client)

        info = await client.get_exchange_info()
        assert info["timezone"] == "UTC"

        klines = await client.get_klines("XAUUSDT", "15m", limit=3, start_time=100, end_time=200)
        assert len(klines) == 3

        premium = await client.get_premium_index("XAUUSDT")
        assert premium["symbol"] == "XAUUSDT"

        ticker = await client.get_ticker_price("XAUUSDT")
        assert ticker["symbol"] == "XAUUSDT"


@pytest.mark.asyncio
async def test_rest_client_handles_http_and_network_errors() -> None:
    """REST client maps HTTP errors and request errors safely."""

    def error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": -1003, "msg": "Too many requests"})

    transport = httpx.MockTransport(error_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = BinanceRestClient(http_client=http_client)

        with pytest.raises(RuntimeError, match="Failed to fetch exchange info: HTTP 429"):
            await client.get_exchange_info()

        with pytest.raises(RuntimeError, match="Failed to fetch klines: HTTP 429"):
            await client.get_klines("XAUUSDT", "15m")

        with pytest.raises(RuntimeError, match="Failed to fetch premiumIndex: HTTP 429"):
            await client.get_premium_index("XAUUSDT")

        with pytest.raises(RuntimeError, match="Failed to fetch ticker price: HTTP 429"):
            await client.get_ticker_price("XAUUSDT")


@pytest.mark.asyncio
async def test_rest_client_handles_network_exceptions() -> None:
    """Network connection exceptions are mapped to clean RuntimeErrors."""

    def network_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    transport = httpx.MockTransport(network_error_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = BinanceRestClient(http_client=http_client)

        with pytest.raises(RuntimeError, match="Network error fetching exchange info"):
            await client.get_exchange_info()

        with pytest.raises(RuntimeError, match="Network error fetching klines"):
            await client.get_klines("XAUUSDT", "15m")

        with pytest.raises(RuntimeError, match="Network error fetching premiumIndex"):
            await client.get_premium_index("XAUUSDT")

        with pytest.raises(RuntimeError, match="Network error fetching ticker price"):
            await client.get_ticker_price("XAUUSDT")
