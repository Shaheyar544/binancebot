---
name: xau-risk
description: Enforce hard capital, leverage, liquidation, exposure, loss, volatility, event, and DCA safety constraints for the XAUUSDT bot.
---
# XAU Risk Engine

RiskEngine is the final gate before execution.

Enforce user funds, leverage, maximum liquidation price, max exposure, max entries, max daily loss, emergency loss, drawdown, volatility, data freshness, event lock, and exchange filters.

Every individual DCA/additional order must be <= $500 notional. Never split a larger DCA to bypass this cap.

Use actual Binance account/position/margin data for liquidation safety where available. If a configuration violates the user's liquidation constraint, reject it without changing user values.

No new entries from 24h before a high-impact event through 24h after it. Existing positions remain under normal risk management.

Any uncertain critical risk input => block new orders.

Build property/invariant tests for every hard rule.
