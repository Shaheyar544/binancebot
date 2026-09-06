---
name: xau-strategy
description: Implement the adaptive XAUUSDT long-only strategy, including regime detection, scoring, WAIT behavior, exits, and post-entry re-analysis.
---
# XAU Strategy

This is adaptive long-only trading, not Grid and not Martingale.

Entry families: breakout + retest; support reclaim; trend pullback.

Gate order:
1. data quality
2. event/news lock
3. 1D bias
4. 4H structure
5. 1H confirmation
6. 15M trigger
7. technical score
8. volatility/liquidity
9. risk approval

Configurable baseline score: 1D 15, 4H 20, 1H 20, 15M 20, EMA 10, RSI/MACD 5, volume 5, R/R 5. Initial threshold 85; preferred 90+.

WAIT/BLOCKED are first-class. Never enter because price fell, because a trade lost money, or because a grid level was reached. After every fill perform a full 15M/1H/4H/1D re-analysis and persist it.
