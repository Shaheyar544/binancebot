# Prompt 02 — Adaptive Strategy

Implement deterministic XAUUSDT long-only analysis and strategy.

Use 1D -> 4H -> 1H -> 15M. Implement structure/BOS/CHoCH, EMA 10/20/50/200, RSI, MACD, ATR, Bollinger, volume, support/resistance, liquidity sweeps and volatility regime.

Implement regimes and configurable scoring. Baseline weighting: 1D 15, 4H 20, 1H 20, 15M 20, EMA 10, RSI/MACD 5, volume 5, R/R 5. Initial threshold 85/100; preferred 90+.

Implement breakout-retest, support reclaim and trend-pullback entries. WAIT and BLOCKED are first-class. Never enter because price is falling, because a previous trade lost money, or because a grid level was reached.

Test bullish, bearish, sideways, high-volatility, stale-data and incomplete-candle cases.
