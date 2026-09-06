"""WebSocket client for streaming Binance Futures public market data."""

import json
import logging
from collections.abc import Callable
from typing import Any

from src.market_data.enums import MarketDataHealth

logger = logging.getLogger("xau_bot.exchange.ws")


class BinanceWebSocketClient:
    """Async WebSocket client for Binance public market streams.

    Strictly read-only. Operates purely as a market data producer.
    """

    def __init__(
        self,
        stream_url: str,
        on_message_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.stream_url = stream_url
        self.on_message_callback = on_message_callback
        self.health = MarketDataHealth.DISCONNECTED
        self.last_message_time: int = 0

    async def handle_raw_message(self, raw: Any) -> None:
        """Process and validate an incoming WebSocket payload safely."""
        try:
            if isinstance(raw, str):
                try:
                    payload = json.loads(raw)
                except Exception:
                    logger.warning("Dropped malformed non-JSON WebSocket message")
                    return
            elif isinstance(raw, dict):
                payload = raw
            else:
                logger.warning("Dropped unexpected payload type: %s", type(raw))
                return

            if not isinstance(payload, dict) or not payload:
                logger.warning("Ignored empty or invalid WebSocket dict payload")
                return

            # Update heartbeat timestamp
            self.last_message_time = int(payload.get("E", self.last_message_time or 0))
            self.health = MarketDataHealth.HEALTHY

            if self.on_message_callback is not None:
                self.on_message_callback(payload)

        except Exception as exc:
            logger.error("Error processing WebSocket message: %s", exc)

    def check_staleness(self, current_time_ms: int, timeout_ms: int = 10000) -> bool:
        """Check if message stream has ceased exceeding the timeout threshold."""
        if self.last_message_time == 0:
            return False

        if (current_time_ms - self.last_message_time) > timeout_ms:
            self.health = MarketDataHealth.STALE
            return True

        self.health = MarketDataHealth.HEALTHY
        return False
