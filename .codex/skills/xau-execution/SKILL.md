---
name: xau-execution
description: Implement safe XAUUSDT order execution, idempotency, fill verification, protective orders, and restart reconciliation with live trading disabled by default.
---
# XAU Execution

Execution may submit only after Strategy approval and RiskEngine approval.

Default safety: LIVE_TRADING=false; ENABLE_ORDER_EXECUTION=false.

Required: idempotent client IDs, exchange-filter validation, pre-submit risk recheck, acknowledgement/fill verification, protective-order verification, cancellation handling and reconciliation.

If order status, account state, WebSocket state or risk data is uncertain: stop new orders, reconcile, never guess.

Tests must prove no real-order path is reachable with live flags disabled.
