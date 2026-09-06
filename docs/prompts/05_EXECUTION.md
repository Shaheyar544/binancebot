# Prompt 05 — Execution and Reconciliation

Implement execution only after RiskEngine is complete and tested.

Default `LIVE_TRADING=false`, `ENABLE_ORDER_EXECUTION=false`.

Implement idempotent order placement, pre-submit RiskEngine recheck, exchange filter validation, acknowledgement/fill verification, protective orders, cancellation handling and restart reconciliation.

On startup/reconnect fetch actual balances, position and open orders, compare to local state, and block new orders while state is uncertain.

Never guess an order status. Never duplicate an order because a response was delayed. Add integration tests using a fake exchange adapter. Prove no real-order path is reachable with live flags disabled.
