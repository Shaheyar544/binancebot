# Prompt 09 — Final Audit

Perform a hostile production-readiness audit of the XAUUSDT bot.

Check hidden Grid/Martingale behavior, long/short leakage, DCA cap bypass, liquidation bypass, news-lock bypass, incomplete-candle lookahead, duplicate orders, stale/reconnected state errors, execution without RiskEngine approval, live execution with flags disabled, secrets in logs/code, hard-coded Binance filters, AI authority over trading, missing reconciliation and missing tests.

Use Graphify to inspect dependency relationships and unexpected execution paths.

Fix P0/P1 issues, then rerun the complete verification suite. Do not claim production readiness unless evidence supports it.
