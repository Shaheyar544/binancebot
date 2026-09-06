# Master Build Prompt — XAUUSDT Adaptive Long-Only Bot

You are the lead engineer for this repository. Build the XAUUSDT adaptive Binance Futures bot strictly from `AGENTS.md`, `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, and the applicable `.codex/skills/*/SKILL.md` files.

## Mandatory process
1. Inspect the repository and skills before changing code.
2. If `graphify-out/graph.json` exists, use Graphify for architecture/relationship questions before broad grep/search.
3. Use the Superpowers workflow where installed: brainstorm/design -> plan -> TDD -> implementation -> review -> verification.
4. For every feature, write failing tests first, then minimal code, then refactor.
5. Work in small phases. Do not jump ahead to live execution.
6. After code changes, run tests/lint/type checks and `graphify update .`.
7. Report exact files changed and verification results.

## Product rules
- XAUUSDT perpetual.
- LONG ONLY.
- No Grid.
- No Martingale.
- Adaptive WAIT behavior is required.
- Every individual DCA/additional order <= $500 notional; never split to bypass.
- No new trades 24h before through 24h after high-impact events.
- Existing positions are not automatically closed solely due to news or negative P&L.
- User funds, leverage and maximum liquidation are immutable unless the user explicitly changes them.
- RiskEngine is the final authority.
- AI/news cannot execute or override RiskEngine.
- Never use liquidation as a stop.
- Live execution remains disabled until explicit final gate.

## Phase discipline
Only implement the phase requested by the current prompt. If a dependency is missing, implement the smallest safe interface/stub plus tests rather than silently changing scope.

## Binance discipline
Use official current Binance documentation for exchange/API behavior. Retrieve exchange filters dynamically. Never guess contract rules or hard-code symbol constraints.

## Safety discipline
If market data, account state, order state, risk inputs, or event data is uncertain, block new orders and reconcile. Never guess.

## Completion discipline
Do not say "done", "working", "production ready", or "safe" unless the relevant tests and verification evidence support the claim.
