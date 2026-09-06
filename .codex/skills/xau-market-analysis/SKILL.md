---
name: xau-market-analysis
description: Build deterministic multi-timeframe XAUUSDT market analysis from completed candles, structure, trend, momentum, volume, liquidity, and volatility.
---
# XAU Market Analysis

Timeframe hierarchy: 1D -> 4H -> 1H -> 15M.

Analyze BOS/CHoCH, swings, liquidity sweeps, EMA 10/20/50/200, RSI, MACD, ATR, Bollinger, volume, S/R, volatility, mark/index divergence and funding/OI/order book where available.

Hard rules:
- No lookahead.
- Completed candles only.
- Higher-timeframe bearish structure blocks new longs.
- High volatility can block entries.
- Analysis produces evidence; it does not by itself place trades.

Return typed analysis with timeframe bias, structure, levels, indicators, volatility, confidence, timestamp and exact candle IDs used.
