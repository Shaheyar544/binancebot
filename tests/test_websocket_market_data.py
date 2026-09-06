"""Tests for WebSocket market data stream handling, resilience, and staleness."""

from typing import Any

import pytest

from src.exchange.websocket import BinanceWebSocketClient
from src.market_data.enums import MarketDataHealth
from tests.fixtures.binance_fixtures import WS_KLINE_PAYLOAD_CLOSED


@pytest.mark.asyncio
async def test_websocket_message_handling() -> None:
    """Valid WebSocket message triggers registered callback."""
    received_payloads: list[dict[str, Any]] = []

    def on_message(msg: dict[str, Any]) -> None:
        received_payloads.append(msg)

    client = BinanceWebSocketClient(
        stream_url="wss://fstream.binance.com/ws/xauusdt@kline_15m",
        on_message_callback=on_message,
    )

    await client.handle_raw_message(WS_KLINE_PAYLOAD_CLOSED)
    assert len(received_payloads) == 1
    assert received_payloads[0]["s"] == "XAUUSDT"
    assert client.health == MarketDataHealth.HEALTHY


@pytest.mark.asyncio
async def test_websocket_malformed_message_handling() -> None:
    """Malformed non-dict or invalid messages are safely ignored without crashing."""
    received_payloads: list[dict[str, Any]] = []

    def on_message(msg: dict[str, Any]) -> None:
        received_payloads.append(msg)

    client = BinanceWebSocketClient(
        stream_url="wss://fstream.binance.com/ws/xauusdt@kline_15m",
        on_message_callback=on_message,
    )

    # Corrupt string or dict
    await client.handle_raw_message("not valid json")
    await client.handle_raw_message({})
    assert len(received_payloads) == 0
    # Still operational
    assert client.health != MarketDataHealth.INVALID


def test_websocket_stream_healthy_within_timeout() -> None:
    """Stream is healthy when message timestamp is within timeout."""
    client = BinanceWebSocketClient(
        stream_url="wss://fstream.binance.com/ws/xauusdt@kline_15m",
    )
    client.last_message_time = 1700000000000

    # 5 seconds later with 10s threshold -> healthy
    assert client.check_staleness(current_time_ms=1700000005000, timeout_ms=10000) is False
    assert client.health == MarketDataHealth.HEALTHY


def test_websocket_stream_stale_when_exceeding_timeout() -> None:
    """Stream transitions to STALE when message timestamp exceeds threshold."""
    client = BinanceWebSocketClient(
        stream_url="wss://fstream.binance.com/ws/xauusdt@kline_15m",
    )
    client.last_message_time = 1700000000000

    # 15 seconds later with 10s threshold -> stale
    assert client.check_staleness(current_time_ms=1700000015000, timeout_ms=10000) is True
    assert client.health == MarketDataHealth.STALE
