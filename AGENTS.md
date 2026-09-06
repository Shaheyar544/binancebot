# XAUUSDT Adaptive Long-Only Bot — Agent Contract

## Mission
Build a production-grade, adaptive **XAUUSDT Binance Futures long-only** bot. The bot must know when to wait. Safety and correctness outrank trade frequency, cleverness, and speed.

## Non-negotiable constraints
- Symbol: `XAUUSDT` perpetual on Binance USDⓈ-M/TradFi perpetuals as supported by the live exchange.
- Direction: LONG ONLY. Never create a short position.
- No Grid strategy. No Martingale. Never increase size because price moved against the bot.
- Every individual DCA/additional order: **<= $500 notional**. Never split one DCA into multiple orders to bypass this cap.
- New entries are blocked during the high-impact-news lock: **24h before through 24h after** the event. Then enter `POST_NEWS_REASSESSMENT`; do not resume automatically until normal technical/risk gates pass.
- Existing positions are not automatically closed merely because news arrives or P&L is negative.
- DCA is allowed only after a fresh full re-analysis confirms thesis, support/reclaim/pullback, momentum/volume/liquidity, risk, liquidation, exposure, and event gates.
- User controls allocated funds, leverage, and maximum liquidation price. Never silently change them.
- Never use liquidation as a stop-loss.
- Live trading is disabled by default: `LIVE_TRADING=false` and `ENABLE_ORDER_EXECUTION=false`.
- API keys must never appear in source, tests, logs, screenshots, exceptions, or commits.
- Do not hard-code Binance tick size, step size, min notional, leverage limits, trading status, or contract metadata. Read and validate exchange metadata dynamically.
- Never use an incomplete candle as a completed candle.
- AI/news/macro is intelligence only. It cannot directly open, add to, or close trades and cannot override RiskEngine.
- RiskEngine is the final authority before execution.

## Required workflow
1. Read this file and the relevant project skill(s).
2. If `graphify-out/graph.json` exists, use Graphify first for codebase questions and relationships.
3. Before implementation, produce/review the implementation plan.
4. Use TDD: failing test -> minimal implementation -> passing test -> refactor.
5. After changes, run targeted tests, full tests where practical, lint/type checks, and Graphify update.
6. Never claim completion without evidence.
7. Keep changes small and auditable.

## Architecture authority
`Strategy Engine -> Risk Engine -> Execution Engine`

AI may enrich Strategy Intelligence, but may not bypass RiskEngine.

## Required decision states
`WAIT`, `BUY`, `ADD`, `PARTIAL_TP`, `EXIT`, `BLOCKED`, `NEWS_LOCK`, `POST_NEWS_REASSESSMENT`, `EMERGENCY_STOP`, `RECONCILING`, `DATA_UNSAFE`.

## Required evidence
Every signal/decision must preserve the exact market snapshot, completed candles used, indicators, regime, risk state, event/news state, decision, reason, and source/timestamp metadata.

## Graphify policy
- If a graph exists, query it before broad grep/search for architecture questions.
- Use `graphify query`, `path`, or `explain` for relationship questions.
- After code changes run `graphify update .`.
- Do not treat `graphify-out/` as source code.

## Definition of done
A feature is not done until tests cover normal and failure paths, safety invariants are tested, no live order can occur accidentally, reconciliation behavior is tested, logs are structured and secret-safe, documentation is updated, and verification commands have been run and reported.
