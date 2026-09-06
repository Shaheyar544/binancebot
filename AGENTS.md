# XAUUSDT Adaptive Long-Only Bot — Agent Contract

## 1. Mission

Build a production-grade, adaptive **XAUUSDT Binance Futures LONG-ONLY trading bot**.

The system must prioritize:

1. Capital safety
2. Correctness
3. Risk control
4. Data integrity
5. Explainability
6. Reliability
7. Trading quality
8. Trade frequency

The bot must know when **NOT to trade**.

`WAIT`, `BLOCKED`, `NEWS_LOCK`, and `DATA_UNSAFE` are valid and often preferable outcomes.

Never sacrifice safety or correctness to create more trades.

---

# 2. Core Trading Constraints

## Instrument

Target:

`XAUUSDT`

Use the Binance USDⓈ-M / TradFi perpetual contract supported by the live exchange.

Never assume contract specifications.

Retrieve and validate exchange metadata dynamically.

---

## Direction

The system is:

**LONG ONLY**

Opening/additional position actions:

`BUY`

Closing/reducing position actions:

`SELL`

`SELL` may only reduce or close an existing LONG position.

Never create a SHORT position.

Do not introduce SHORT support "for future use."

Illegal short-side states should be impossible to construct through domain models.

---

## Forbidden Strategies

Never implement:

- Martingale
- Fixed Grid trading
- Loss-based position escalation
- Blind averaging down
- Revenge trading
- Automatic size increases because P&L is negative
- Liquidation-based stop logic

An adverse price move alone is NEVER sufficient justification for another entry.

---

# 3. Trading Authority Hierarchy

The mandatory authority chain is:

Strategy Engine
    ↓
Risk Engine
    ↓
Execution Engine

**RiskEngine is the final authority before execution.**

Strategy Engine cannot bypass RiskEngine.

Execution Engine cannot bypass RiskEngine.

AI/news/macro intelligence cannot bypass RiskEngine.

No alternative execution path may exist that avoids the RiskEngine.

---

# 4. User-Controlled Risk Parameters

The following parameters belong exclusively to the user:

- allocated funds
- leverage
- maximum acceptable liquidation price

They must:

- be explicitly configured
- never receive hidden trading defaults
- never be silently changed
- never be automatically optimized
- never be increased or decreased by AI
- never be changed merely to make validation pass

If the requested configuration cannot satisfy safety requirements:

**REJECT THE CONFIGURATION.**

Explain why.

Never silently modify the user's settings.

Other configured risk limits must also never be silently changed, including:

- maximum daily loss
- risk per trade
- emergency loss limit
- maximum exposure
- maximum entries
- maximum holding time
- funding limits
- DCA limits

---

# 5. Liquidation Safety

`max_acceptable_liquidation_price` means:

> The highest liquidation-price value the user is willing to accept.

If the verified/estimated liquidation price is ABOVE this threshold, the configuration is unsafe.

Reject it.

Never automatically modify:

- leverage
- allocated funds
- entry size
- liquidation threshold

to force validation to pass unless a future feature explicitly asks the user to approve a proposed change.

Never use liquidation as a stop-loss.

Maintain a safety buffer between normal risk exits and liquidation.

---

## Binance Liquidation Calculation

Do NOT invent or rely on a simplified generic liquidation formula for live risk decisions.

Binance-specific liquidation calculations must use authoritative exchange/account/position/margin information when implemented.

Domain code should expose an explicit liquidation estimation/validation interface.

If reliable liquidation information is unavailable:

`DATA_UNSAFE`

or

`BLOCKED`

must be preferred over guessing.

---

# 6. DCA / Additional Entry Rules

Every individual DCA/additional order has the hard limit:

`MAX_DCA_NOTIONAL = Decimal("500")`

Rules:

- `$500.00` -> allowed by this invariant
- `$500.01` -> BLOCKED
- `$700` -> BLOCKED
- `$1000` -> BLOCKED

Never split an oversized DCA into multiple smaller orders to bypass the limit.

Example:

A requested `$900` DCA must NOT become:

- `$500`
- `$400`

It must be rejected as an oversized DCA request.

The $500 rule is an individual-order safety ceiling, not permission to trade.

---

## DCA Qualification

Never DCA simply because:

- price fell
- trade is losing
- P&L is negative
- average entry could improve

Before EVERY additional entry, perform a fresh analysis.

DCA requires confirmation that all applicable conditions remain acceptable, including:

- original bullish thesis remains valid
- 1D structure
- 4H structure
- 1H confirmation
- 15M setup
- support/reclaim/pullback quality
- market structure
- momentum
- volume
- liquidity
- volatility
- exposure
- liquidation safety
- daily risk
- emergency risk
- maximum entries
- maximum total exposure
- event/news state
- execution safety

If evidence is insufficient:

`WAIT`

or

`BLOCKED`

No blind averaging.

---

# 7. High-Impact News Policy

High-impact events trigger a strict new-entry lock.

For each qualifying high-impact event:

**24 hours before event**
through
**24 hours after event**

state:

`NEWS_LOCK`

During `NEWS_LOCK`:

- no new LONG entry
- no new DCA/additional entry
- no AI-generated entry
- no strategy may override the lock

After the 24-hour post-event period expires:

enter:

`POST_NEWS_REASSESSMENT`

Do NOT automatically resume trading.

Perform fresh:

- 15M analysis
- 1H analysis
- 4H analysis
- 1D analysis
- volatility analysis
- structure analysis
- support/resistance analysis
- liquidity analysis
- volume/momentum analysis
- macro/news reassessment
- RiskEngine validation

Only normal technical + risk qualification may return the bot to an entry-capable state.

---

# 8. Existing Positions During News

Do NOT automatically close an existing position merely because:

- high-impact news is approaching
- high-impact news occurred
- the position is losing
- P&L became negative

Existing positions require fresh risk/thesis analysis.

Valid outcomes may include:

`WAIT`

`PARTIAL_TP`

`EXIT`

`EMERGENCY_STOP`

DCA remains prohibited while the high-impact-news lock is active.

RiskEngine emergency protections always retain authority.

---

# 9. AI / News / Macro Authority

AI is an **intelligence layer**, not an execution authority.

AI may:

- summarize news
- classify macro conditions
- analyze gold-related catalysts
- assess USD/Fed/rate context
- assign confidence
- identify risk
- explain market context
- recommend further analysis

AI may NOT directly:

- open a trade
- add/DCA
- close a trade
- place an order
- bypass technical confirmation
- bypass news locks
- bypass RiskEngine
- modify user risk configuration
- enable live execution

AI output is advisory input to the deterministic system.

---

## AI Evidence Classification

Where applicable, distinguish:

- `FACT`
- `EXPECTATION`
- `ANALYSIS`
- `AI_INTERPRETATION`

AI assessments should preserve:

- timestamp
- source
- freshness
- confidence
- reasoning

Rumors must never be represented as confirmed facts.

---

# 10. Market Data Integrity

Never use an incomplete candle as a completed candle.

Primary analysis timeframes:

- `15M`
- `1H`
- `4H`
- `1D`

Completed-candle analysis must only consume finalized candles.

Every signal must know exactly which candle versions were used.

Never silently substitute missing market data.

---

# 11. Temporal Integrity / No Lookahead

Historical decisions may use only information available at the decision timestamp.

Never introduce lookahead bias.

Never use:

- future candles
- future highs/lows
- future indicator values
- future news outcomes
- future event results
- future funding information
- future open interest
- future market structure
- revised future data unavailable at the historical timestamp

This applies especially to:

- backtests
- simulations
- signal reconstruction
- strategy evaluation
- AI historical analysis

Backtest correctness outranks attractive results.

---

# 12. Financial Precision

Use Python `Decimal` for financial calculations and persisted financial values.

Never use binary floating-point arithmetic for:

- price
- quantity
- notional
- leverage
- margin
- liquidation price
- P&L
- fees
- funding
- risk limits
- exposure
- account balances
- DCA limits

Convert external numeric values into `Decimal` at system boundaries.

Never construct Decimal financial values from an imprecise float when the original string/decimal representation is available.

---

# 13. Binance Metadata

Never hard-code:

- tick size
- step size
- minimum quantity
- maximum quantity
- minimum notional
- maximum notional
- leverage limits
- leverage brackets
- maintenance margin rules
- liquidation rules
- contract status
- symbol trading status
- quantity precision
- price precision
- funding assumptions

Retrieve applicable exchange metadata dynamically from Binance.

Validate it before trading.

Cache only where safe.

Refresh when required.

If critical metadata is missing, stale, invalid, or contradictory:

`DATA_UNSAFE`

Do not guess.

---

# 14. No Hidden Fallbacks

Never replace unavailable or invalid information with guessed trading values.

This applies to:

- market data
- exchange metadata
- account state
- position state
- liquidation information
- risk information
- funding
- order state
- event/news information when required
- configuration

Never write logic equivalent to:

> "Data unavailable, therefore use a reasonable default."

When required information is unavailable:

prefer:

`DATA_UNSAFE`

`BLOCKED`

`WAIT`

or fail startup when appropriate.

Fail closed, not open.

---

# 15. Live Trading Safety

Live execution is disabled by default:

`LIVE_TRADING=false`

`ENABLE_ORDER_EXECUTION=false`

No code path may place, modify, or cancel a live Binance order unless BOTH flags are explicitly enabled.

If either flag is false:

live execution must fail closed.

Every live execution entry point must independently respect the execution gate or pass through a single mandatory gated execution boundary.

Never silently enable live trading based on:

- environment
- deployment mode
- API key presence
- configuration migration
- test mode
- dashboard action
- AI instruction

Live trading requires explicit configuration.

---

# 16. Secrets & Credential Security

Binance credentials must never appear in:

- source code
- committed configuration
- tests
- logs
- screenshots
- exceptions
- tracebacks where preventable
- object repr
- debug output
- database audit text
- commits

Use secret-aware configuration types.

Apply structured redaction to logs.

Redaction must work even when a secret appears inside a larger string.

`.env` must never be committed.

Only safe templates such as `.env.example` may exist in source control.

Never grant withdrawal permissions to trading API credentials.

---

# 17. Required Decision States

The domain must support:

`WAIT`

`BUY`

`ADD`

`PARTIAL_TP`

`EXIT`

`BLOCKED`

`NEWS_LOCK`

`POST_NEWS_REASSESSMENT`

`EMERGENCY_STOP`

`RECONCILING`

`DATA_UNSAFE`

Decision states must have explicit reasons.

Avoid ambiguous boolean-only trading decisions.

---

# 18. Decision Evidence & Auditability

Every signal/decision must preserve enough immutable evidence to reconstruct WHY it occurred.

Where applicable preserve:

- symbol
- timestamp
- decision state
- completed candles used
- timeframe states
- OHLCV
- mark price
- index price
- last price
- indicators
- market structure
- regime
- support/resistance
- liquidity context
- volume
- momentum
- volatility
- funding
- open interest where available
- technical score
- macro score
- event/news state
- risk state
- exposure
- position state
- liquidation state
- decision
- reason
- source metadata
- freshness metadata
- AI confidence where applicable

Historical decision snapshots should be immutable.

Do not rewrite historical evidence to match later market information.

---

# 19. Restart & Reconciliation Safety

After restart, disconnect, timeout, WebSocket failure, uncertain order response, or account-state uncertainty:

enter:

`RECONCILING`

Before new execution:

1. retrieve actual Binance account state
2. retrieve actual XAUUSDT position
3. retrieve relevant open orders
4. reconcile local state
5. recalculate risk
6. verify liquidation/exposure
7. detect duplicate/unknown orders
8. restore authoritative state

Never assume the local database is more authoritative than the exchange for live exchange state.

While execution state is uncertain:

NO NEW ORDERS.

Prefer reconciliation over guessing.

---

# 20. Idempotency & Duplicate Protection

Execution must eventually support deterministic client/order identifiers.

Retries must not create duplicate trades.

Network uncertainty must never be interpreted as proof that an order failed.

Before retrying uncertain execution:

reconcile with Binance.

Duplicate-order prevention is mandatory.

---

# 21. Emergency Safety

Emergency protection may override normal Strategy decisions.

Examples include:

- corrupted market data
- account mismatch
- impossible position state
- liquidation danger
- severe risk-limit breach
- exchange-state contradiction
- unrecoverable reconciliation failure
- execution integrity failure

Appropriate states include:

`EMERGENCY_STOP`

`DATA_UNSAFE`

`RECONCILING`

Safety actions must be explainable and auditable.

---

# 22. Required Engineering Workflow

For every implementation task:

1. Read `AGENTS.md`.
2. Read relevant project documentation.
3. Read applicable project Agent Skills.
4. Inspect the current implementation before changing it.
5. Use Graphify first for architecture/relationship questions when a graph exists.
6. Produce or review an implementation plan.
7. Identify applicable safety invariants.
8. Write failing tests first.
9. Implement the smallest correct change.
10. Make tests pass.
11. Refactor only after correctness.
12. Run targeted tests.
13. Run the broader/full test suite when practical.
14. Run Ruff.
15. Run mypy.
16. Update Graphify after source changes.
17. Review the final diff.
18. Update documentation when behavior/contracts change.
19. Report verification evidence.
20. Never claim completion without verification.

Keep changes small, auditable, and reversible.

---

# 23. TDD Policy

Use:

**RED -> GREEN -> REFACTOR**

RED:
Write a test demonstrating required behavior or failure protection.

GREEN:
Implement the minimum correct behavior.

REFACTOR:
Improve structure without changing verified behavior.

Safety invariants require explicit tests.

Never weaken or delete a safety test merely to make CI pass.

If a test conflicts with a newer explicit project requirement:

document the conflict and update the contract/test deliberately.

---

# 24. Graphify Policy

If:

`graphify-out/graph.json`

exists, use Graphify before broad grep/search for architectural questions.

Preferred tools:

`graphify query`

for architectural questions.

`graphify path`

for dependency/relationship tracing.

`graphify explain`

for focused concept investigation.

After source changes run:

`graphify update .`

Do not treat:

`graphify-out/`

as application source code.

Do not manually edit generated graph output.

If Graphify is unavailable:

report that fact.

Never claim Graphify verification occurred when it did not.

---

# 25. Code Quality Rules

Prefer:

- explicit types
- small focused modules
- pure deterministic functions where practical
- dependency injection at external boundaries
- immutable domain models
- explicit state machines
- structured errors
- structured logging
- async-safe exchange/database boundaries
- testable interfaces

Avoid:

- hidden global state
- giant god classes
- implicit side effects
- broad exception swallowing
- magic numbers
- duplicated safety logic
- unnecessary abstractions
- speculative features
- premature optimization

Financial and safety constants must be named.

---

# 26. External Boundary Design

Treat these as external/untrusted boundaries:

- Binance REST
- Binance WebSocket
- news providers
- economic calendars
- AI providers
- database
- environment variables
- dashboard/user input

Validate external data before it enters trusted domain logic.

Domain and RiskEngine behavior should remain testable without requiring live Binance access.

---

# 27. Source Authority

For Binance behavior and contract mechanics:

prefer official Binance documentation and live exchange metadata.

For economic events:

prefer authoritative primary sources where available, including relevant official U.S. agencies.

Do not hard-code event calendars that change over time.

External information must carry timestamps/freshness where relevant.

---

# 28. AI Coding-Agent Rules

Coding agents must not invent missing requirements.

If requirements are genuinely ambiguous and the choice affects:

- financial risk
- live execution
- liquidation
- position sizing
- DCA
- account state
- news locking
- user-controlled configuration

STOP and request clarification.

For low-risk implementation details, choose the smallest conventional solution consistent with existing architecture.

Do not expand scope without justification.

Do not implement future phases during the current phase unless required by an interface/contract.

TODOs must clearly state why the implementation is deferred.

---

# 29. Phase Discipline

Implement only the currently authorized phase.

Future functionality may receive:

- interfaces
- protocols
- typed contracts
- test doubles
- TODO documentation

but not premature production implementation.

In particular, early foundation phases must not accidentally introduce executable live-trading paths.

---

# 30. Testing Safety-Critical Failure Paths

Tests must cover both successful and unsafe scenarios.

Safety-critical components must test conditions such as:

- execution gate disabled
- one execution flag disabled
- invalid user configuration
- oversized DCA
- attempted short state
- incomplete candle
- stale/missing data
- invalid exchange metadata
- unsafe liquidation
- duplicate execution attempt
- uncertain order state
- reconciliation requirement
- secret leakage
- news lock
- risk rejection

A feature is incomplete if only the happy path is tested.

---

# 31. Verification Commands

Use project-configured commands.

Expected baseline:

`uv run pytest -v`

`uv run ruff check .`

`uv run mypy src tests`

If formatting checks are configured:

`uv run ruff format --check .`

After applicable source changes:

`graphify update .`

Never report a command as passing unless it was actually executed successfully.

---

# 32. Completion Report

At the end of an implementation task report:

1. What changed
2. Files created
3. Files modified
4. Tests added/updated
5. Test results
6. Ruff result
7. Mypy result
8. Graphify result
9. Safety invariants verified
10. Known limitations
11. TODOs
12. Assumptions
13. Recommended next phase

Never describe an unfinished phase as:

"production ready"

unless the complete production-readiness requirements have actually been satisfied.

---

# 33. Definition of Done

A feature is NOT done until:

- required behavior is implemented
- normal paths are tested
- failure paths are tested
- applicable financial invariants are tested
- live execution cannot occur accidentally
- long-only protection remains intact
- DCA cap cannot be bypassed
- user risk settings cannot be silently changed
- stale/unsafe data fails closed
- secrets remain protected
- reconciliation behavior is tested where applicable
- duplicate execution is prevented where applicable
- logs are structured and secret-safe
- documentation reflects behavioral changes
- verification commands have actually been run
- verification results have been reported
- final diff has been reviewed

Safety > correctness > reliability > explainability > performance > trade frequency.

When uncertain:

**DO NOT TRADE.**