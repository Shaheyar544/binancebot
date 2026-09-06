---
name: xau-backtesting
description: Build an event-driven no-lookahead XAUUSDT backtester that models fills, fees, funding, leverage, liquidation, DCA, news locks, and risk rules.
---
# XAU Backtesting

Required: event-driven simulation, completed-candle semantics, no lookahead, fees, funding, slippage, spread, fills, margin, leverage, liquidation, DCA <= $500, news lock, daily/emergency limits.

Metrics: return, profit factor, win rate, avg/median trade, max DD, MAE/MFE, Sharpe/Sortino/Calmar, trades, holding time, fees/funding, max exposure, max adds, worst losing sequence, liquidations, and $5/$10/$20/$30/$50 target hit rates.

Validate with walk-forward/OOS and stress scenarios: 5/10/15/20% drops, V-recovery, prolonged downtrend, sideways, bull, extreme volatility.

Never optimize only for total P&L.
