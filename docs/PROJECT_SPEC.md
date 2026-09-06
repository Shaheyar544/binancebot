# XAUUSDT Adaptive Long-Only Bot — Project Specification

## Product
A 24/7 adaptive Binance Futures bot for XAUUSDT that takes long positions only when a multi-timeframe technical thesis, macro/event filter, and risk engine all agree. `WAIT` is a normal and preferred result when evidence is weak.

## User-controlled configuration
Required: allocated funds, leverage, maximum acceptable liquidation price.
Optional: profit target, maximum entries, maximum daily loss, risk per trade, emergency loss limit, maximum total exposure, maximum holding time, funding threshold.

The bot calculates sizing and strategy around these settings. If constraints are incompatible, reject the configuration and explain why. Never silently modify user settings.

## Timeframes
1D = macro trend; 4H = structure; 1H = confirmation; 15M = execution.

## Technical model
Track market structure/BOS/CHoCH, swing highs/lows, liquidity sweeps, EMA 10/20/50/200, RSI, MACD, ATR, Bollinger Bands, volume, support/resistance, volatility, price/mark/index relationship, funding/OI where available, and order-book/liquidity data where available.

Suggested score: 1D 15, 4H 20, 1H 20, 15M 20, EMA 10, RSI/MACD 5, volume 5, R/R 5. Minimum initial entry score 85/100; preferred 90+. Keep configurable.

## Regimes
`STRONG_BULL`, `BULL`, `BULLISH_RANGE`, `NEUTRAL`, `BEARISH_RANGE`, `BEAR`, `STRONG_BEAR`, `HIGH_VOLATILITY`, `EVENT_RISK`.

No new long when higher-timeframe structure is invalid/bearish.

## Entry families
- breakout + retest
- support reclaim
- trend pullback

No entry solely because price is low or because an existing position is losing.

## Additional entries / DCA
Each additional order must be <= **$500 notional**. Never split an oversized DCA into multiple orders to bypass the rule.

DCA requires a fresh high-quality setup, bullish 1D/4H/1H thesis, 15M trigger/support/reclaim, volume/momentum/liquidity confirmation, acceptable volatility, no news lock, available max entries/exposure, liquidation constraint pass, daily/emergency risk pass, acceptable R/R, and no thesis invalidation.

## News and macro
High-impact policy: lock new entries 24h before the event through 24h after it; existing positions remain under normal risk/exit management; after the lock enter `POST_NEWS_REASSESSMENT`; resume only after normal technical and risk gates pass.

AI/news must label `FACT`, `EXPECTATION`, `ANALYSIS`, or `AI_INTERPRETATION`.

Use official sources first: Federal Reserve, BLS, BEA, U.S. Treasury. Reputable financial reporting can add context. Rumors are not facts.

Track FOMC, CPI, NFP, PPI, PCE, GDP, Retail Sales, ISM, JOLTS, ADP, Jobless Claims, Consumer Confidence, University of Michigan inflation expectations, Treasury announcements, and major geopolitical events.

## Position management
After every fill: retrieve actual account/position state; recalculate average entry, notional, margin and liquidation estimate; run full 15M/1H/4H/1D re-analysis; reevaluate stop/invalidation, TP, DCA eligibility and event risk; save an immutable post-entry snapshot.

## Exits
Dynamic target/invalidation may use configured profit goal, ATR, resistance/swing high, Bollinger context, momentum/volume and regime.

Invalidation can be 15M structure failure, 1H support failure, 4H bullish structure break, ATR emergency stop, abnormal volatility, mark/index divergence, or unsafe data/API state. Never wait for liquidation.

## Risk
RiskEngine enforces max liquidation constraint, max exposure, max entries, max daily loss, emergency loss, drawdown, funding constraints if configured, volatility lock, event lock, data safety and exchange filters.

Liquidation must use actual Binance account/position/margin data where possible, not a generic formula alone.

## Infrastructure
Hostinger KVM VPS, 24/7. Suggested stack: Python, Binance official REST/WebSocket interfaces, SQLite V1, FastAPI dashboard/API, optional Supabase for dashboard data/realtime/auth, Telegram/n8n for alerts. Trading engine must remain functional without dashboard.

## Modes
Backtest -> Paper -> Shadow -> Live. Live requires both execution flags plus explicit user confirmation.

## Observability
Every decision explains what happened, what was checked, what passed, what failed, why the action was chosen, and what must change for the next action.
