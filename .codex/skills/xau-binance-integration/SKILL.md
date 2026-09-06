---
name: xau-binance-integration
description: Safely implement Binance XAUUSDT market-data, account, WebSocket, exchange-filter, and reconciliation code without hard-coded contract assumptions.
---
# XAU Binance Integration

Use for Binance REST/WebSocket, exchange metadata, account state, positions, orders, mark/index/funding/OI, reconnects, and reconciliation.

Rules:
- Verify current Binance documentation before relying on an endpoint or field.
- Read symbol filters dynamically; never hard-code tick size, step size, min notional, leverage limits, status, or contract metadata.
- Treat mark, index and last price as distinct.
- Never use incomplete candles in strategy decisions.
- WebSocket disconnect/gap => data unsafe until repaired.
- Block new orders while account state is uncertain.
- Use idempotent client order IDs and verify fills.
- On restart reconcile balances, position, open orders and local DB before trading.
- Secrets never enter logs/errors/tests.

Required tests: dynamic filters, stale feed, reconnect, duplicate-order prevention, restart reconciliation, incomplete-candle rejection, exchange-error mapping.
