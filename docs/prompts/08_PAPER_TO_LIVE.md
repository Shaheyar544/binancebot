# Prompt 08 — Paper/Shadow/Live Gate

Prepare staged deployment: Backtest -> Paper -> Shadow -> Live.

Paper and Shadow use live market data but no real order placement.

Before live verify: all tests green; lint/type/security checks green; backtest reviewed; paper/shadow reviewed; reconciliation tested; news lock tested; DCA cap tested; liquidation constraint tested; kill switch tested; secrets absent; execution flags remain disabled until explicit confirmation.

Produce a pre-flight report. Do not enable live trading automatically.
