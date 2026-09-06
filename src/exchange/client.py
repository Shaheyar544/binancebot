"""Read-only Binance Futures REST client for market data and metadata."""

import logging
from typing import Any

import httpx

logger = logging.getLogger("xau_bot.exchange.rest")


class BinanceRestClient:
    """Async read-only REST client for Binance USDⓈ-M Futures.

    Strictly limited to public market data and metadata endpoints.
    Has zero order placement, modification, or cancellation capabilities.
    """

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None

    async def get_exchange_info(self) -> dict[str, Any]:
        """Fetch current exchange metadata and symbol rules dynamically."""
        url = f"{self.base_url}/fapi/v1/exchangeInfo"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("Binance exchangeInfo HTTP error %d", exc.response.status_code)
            raise RuntimeError(
                f"Failed to fetch exchange info: HTTP {exc.response.status_code}"
            ) from None
        except httpx.RequestError as exc:
            logger.error("Binance exchangeInfo network error: %s", exc)
            raise RuntimeError(f"Network error fetching exchange info: {exc}") from None

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[list[Any]]:
        """Fetch historical candlestick bars."""
        url = f"{self.base_url}/fapi/v1/klines"
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            data: list[list[Any]] = response.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("Binance klines HTTP error %d", exc.response.status_code)
            raise RuntimeError(f"Failed to fetch klines: HTTP {exc.response.status_code}") from None
        except httpx.RequestError as exc:
            logger.error("Binance klines network error: %s", exc)
            raise RuntimeError(f"Network error fetching klines: {exc}") from None

    async def get_premium_index(self, symbol: str) -> dict[str, Any]:
        """Fetch mark price, index price, and funding rate."""
        url = f"{self.base_url}/fapi/v1/premiumIndex"
        try:
            response = await self._client.get(url, params={"symbol": symbol.upper()})
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("Binance premiumIndex HTTP error %d", exc.response.status_code)
            raise RuntimeError(
                f"Failed to fetch premiumIndex: HTTP {exc.response.status_code}"
            ) from None
        except httpx.RequestError as exc:
            logger.error("Binance premiumIndex network error: %s", exc)
            raise RuntimeError(f"Network error fetching premiumIndex: {exc}") from None

    async def get_ticker_price(self, symbol: str) -> dict[str, Any]:
        """Fetch latest market trade price."""
        url = f"{self.base_url}/fapi/v1/ticker/price"
        try:
            response = await self._client.get(url, params={"symbol": symbol.upper()})
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data
        except httpx.HTTPStatusError as exc:
            logger.error("Binance ticker price HTTP error %d", exc.response.status_code)
            raise RuntimeError(
                f"Failed to fetch ticker price: HTTP {exc.response.status_code}"
            ) from None
        except httpx.RequestError as exc:
            logger.error("Binance ticker price network error: %s", exc)
            raise RuntimeError(f"Network error fetching ticker price: {exc}") from None

    async def close(self) -> None:
        """Close underlying HTTP client if owned."""
        if self._owns_client:
            await self._client.aclose()
