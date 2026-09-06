# Prompt 06 — Event-Driven Backtester

Build an event-driven no-lookahead backtester using the same Strategy and RiskEngine logic as production.

Simulate fills, fees, funding, slippage, spread, margin, leverage, liquidation, DCA <= $500, news lock, daily loss and emergency stops.

Produce walk-forward and out-of-sample results plus stress tests: 5/10/15/20% drops, V-recovery, prolonged downtrend, sideways, bull and extreme volatility.

Report P&L plus profit factor, win rate, max drawdown, MAE/MFE, Sharpe/Sortino/Calmar, fees, funding, max exposure, max adds, losing streaks, liquidations and target-hit rates.

Add regression fixtures so strategy changes cannot silently change historical behavior.
