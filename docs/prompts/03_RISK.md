# Prompt 03 — Risk Engine

Implement the XAUUSDT RiskEngine before any live execution code.

Enforce user funds, leverage, maximum liquidation price, maximum exposure, maximum entries, daily loss, emergency loss, drawdown, volatility, data freshness, event lock and exchange filters.

Every individual DCA/additional order must be <= $500 notional. A larger desired addition must be rejected, never split to bypass the rule.

Calculate liquidation safety from actual Binance account/position/margin data where available. If configuration cannot satisfy the user's liquidation constraint, reject it without changing the user's values.

RiskEngine is the final authority. Strategy and AI cannot override it. Create property/invariant tests for every hard rule and prove unsafe inputs cannot reach ExecutionEngine.
