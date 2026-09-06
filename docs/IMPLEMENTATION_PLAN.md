# Implementation Plan

## Phase 0 — Agent/repository foundation
Python project, Graphify, Superpowers workflow, optional UI skills, AGENTS.md, project skills, lint/type/test tooling, `.env.example`, disabled-live gates, baseline tests.

## Phase 1 — Configuration/domain
Typed config and immutable domain models. Test required config, incompatible liquidation, unchanged user values, DCA > $500.

## Phase 2 — Binance market data
Exchange info, klines, mark/index, funding, OI, order book, WebSocket reconnect, completed-candle store. Test dynamic filters, stale feed, reconnect and incomplete candle exclusion.

## Phase 3 — Technical analysis
Structure, trend, momentum, volume, S/R, volatility, regime using deterministic fixtures and no lookahead.

## Phase 4 — Signal engine
Breakout/retest, reclaim, pullback, scoring, WAIT/BLOCKED and full explanation.

## Phase 5 — Risk engine
Liquidation safety, sizing, exposure, daily loss, emergency loss, DCA cap, event lock and data safety. Complete before live execution code.

## Phase 6 — Backtester
Event-driven, no lookahead; fees, funding, slippage, fills, margin, liquidation, DCA, news lock, daily limits, walk-forward/OOS, stress tests.

## Phase 7 — Execution/reconciliation
Order manager, idempotency, fill verification, protective orders, restart recovery and reconciliation. Live stays disabled.

## Phase 8 — Macro/news
Official calendars, freshness, AI interpretation, 24h lock, post-news reassessment and immutable AI records.

## Phase 9 — Dashboard
Overview, signal explanations, risk/liquidation, DCA review, events, backtests and health.

## Phase 10 — Paper/Shadow
Live data, no real orders. Validate decisions and state reconciliation.

## Phase 11 — Live gate
Only after tests, backtest, paper/shadow evidence, secrets checks, kill-switch tests and explicit user confirmation.
