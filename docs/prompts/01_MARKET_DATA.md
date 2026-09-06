# Prompt 01 — Binance Market Data

Implement the Binance XAUUSDT market-data layer using official Binance documentation as authority.

Dynamically retrieve exchange metadata and validate all symbol filters. Implement REST + WebSocket market data for 15M/1H/4H/1D, mark price, index price, funding, OI and order-book/liquidity data where available.

Never hard-code tick size, step size, min notional, leverage limits, trading status or contract metadata. Only completed candles enter the strategy store. Handle reconnects, stale feeds, sequence gaps and server time correctly.

Write tests first for malformed messages, duplicates, stale data, incomplete candles and reconnect recovery. Do not implement order execution in this phase.
