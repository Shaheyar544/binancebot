import hashlib
import hmac
import logging
import time
from decimal import Decimal
from typing import Any, Protocol

import httpx

from src.domain.enums import PositionSide
from src.domain.models import OrderIntent, PositionSnapshot
from src.execution.models import ExecutionStatus, OrderExecutionResult

logger = logging.getLogger("xau_bot.execution.binance_adapter")


class ExchangeAdapter(Protocol):
    """Protocol for exchange order routing and state polling."""

    async def submit_order(self, intent: OrderIntent) -> OrderExecutionResult:
        """Submit order to exchange."""
        ...

    async def get_position(self, symbol: str) -> PositionSnapshot | None:
        """Get current position from exchange."""
        ...

    async def get_raw_position(self, symbol: str) -> dict[str, Any] | None:
        """Get raw position data for boundary verification."""
        ...


class FakeExchangeAdapter:
    """In-memory test double for exchange operations."""

    def __init__(self) -> None:
        self.orders: dict[str, OrderIntent] = {}
        self.position: PositionSnapshot | None = None
        self.raw_position_data: dict[str, Any] | None = None

    def set_position(self, position: PositionSnapshot | None) -> None:
        """Set active position state for testing."""
        self.position = position
        if position is not None:
            self.raw_position_data = {
                "symbol": position.symbol,
                "positionAmt": str(position.size),
                "entryPrice": str(position.entry_price),
            }
        else:
            self.raw_position_data = None

    def inject_raw_short_state(self, symbol: str, size: Decimal, entry_price: Decimal) -> None:
        """Simulate illegal exchange short position for safety invariant testing."""
        self.raw_position_data = {
            "symbol": symbol,
            "positionAmt": str(size),  # Negative indicates short
            "entryPrice": str(entry_price),
        }
        self.position = None

    async def submit_order(self, intent: OrderIntent) -> OrderExecutionResult:
        """Simulate instantaneous limit order fill."""
        self.orders[intent.client_order_id] = intent
        return OrderExecutionResult(
            client_order_id=intent.client_order_id,
            exchange_order_id=f"EXCH_{intent.client_order_id}",
            status=ExecutionStatus.FILLED,
            filled_qty=intent.quantity,
            avg_price=intent.price,
            fee_paid=intent.notional * Decimal("0.0005"),
            timestamp=int(time.time() * 1000),
        )

    async def get_position(self, symbol: str) -> PositionSnapshot | None:
        """Retrieve simulated position."""
        return self.position

    async def get_raw_position(self, symbol: str) -> dict[str, Any] | None:
        """Retrieve raw exchange position payload."""
        return self.raw_position_data


class BinanceFuturesLiveAdapter:
    """Live exchange adapter executing orders directly against Binance Futures API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = "https://testnet.binancefuture.com",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(timeout=10.0)

    def _sign_query(self, query: str) -> str:
        """Generate HMAC-SHA256 signature for signed endpoints."""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def submit_order(self, intent: OrderIntent) -> OrderExecutionResult:
        """Submit limit order to Binance Futures API."""
        now_ms = int(time.time() * 1000)
        query = (
            f"symbol={intent.symbol}&side={intent.side.value}&type={intent.order_type}"
            f"&quantity={intent.quantity}&price={intent.price}&timeInForce=GTC"
            f"&newClientOrderId={intent.client_order_id}&timestamp={now_ms}"
        )
        sig = self._sign_query(query)
        headers = {"X-MBX-APIKEY": self.api_key}

        url = f"{self.base_url}/fapi/v1/order?{query}&signature={sig}"
        resp = await self._client.post(url, headers=headers)
        if resp.status_code != 200:
            logger.error("Binance order placement rejected: %s", resp.text)
            raise RuntimeError(f"Binance order rejected: {resp.text}")

        data = resp.json()
        status = (
            ExecutionStatus.FILLED if data.get("status") == "FILLED" else ExecutionStatus.SUBMITTED
        )
        return OrderExecutionResult(
            client_order_id=intent.client_order_id,
            exchange_order_id=str(data.get("orderId", "")),
            status=status,
            filled_qty=Decimal(str(data.get("executedQty", "0"))),
            avg_price=Decimal(str(data.get("avgPrice", str(intent.price)))),
            fee_paid=Decimal("0.0"),
            timestamp=int(data.get("updateTime", now_ms)),
        )

    async def get_raw_position(self, symbol: str) -> dict[str, Any] | None:
        """Fetch raw positionRisk payload from Binance."""
        now_ms = int(time.time() * 1000)
        query = f"symbol={symbol}&timestamp={now_ms}"
        sig = self._sign_query(query)
        headers = {"X-MBX-APIKEY": self.api_key}

        url = f"{self.base_url}/fapi/v2/positionRisk?{query}&signature={sig}"
        resp = await self._client.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error("Failed to fetch positionRisk from Binance: %s", resp.text)
            return None

        positions: list[dict[str, Any]] = resp.json()
        for p in positions:
            if p.get("symbol") == symbol:
                return p
        return None

    async def get_position(self, symbol: str) -> PositionSnapshot | None:
        """Fetch parsed PositionSnapshot from Binance."""
        raw = await self.get_raw_position(symbol)
        if raw is None:
            return None

        size = Decimal(str(raw.get("positionAmt", "0.0")))
        if size == Decimal("0.0"):
            return None

        entry_price = Decimal(str(raw.get("entryPrice", "0.0")))
        leverage = Decimal(str(raw.get("leverage", "1.0")))
        unrealized = Decimal(str(raw.get("unRealizedProfit", "0.0")))
        liq_price = Decimal(str(raw.get("liquidationPrice", "0.0")))

        return PositionSnapshot(
            symbol=symbol,
            side=PositionSide.LONG,
            size=size,
            entry_price=entry_price,
            leverage=leverage,
            margin=(size * entry_price) / leverage,
            liquidation_price=liq_price,
            unrealized_pnl=unrealized,
        )
