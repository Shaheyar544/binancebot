---
name: xau-qa
description: Verify XAUUSDT bot changes with invariant tests, integration tests, security checks, Graphify updates, and evidence-based completion.
---
# XAU QA

Before coding: identify skills, inspect graph if present, define acceptance tests.
During coding: TDD, deterministic fixtures, failure-path tests, idempotency tests, restart/reconciliation tests.

Safety invariants:
- long only
- no Grid/Martingale behavior
- DCA <= $500
- no new trade in news lock
- no trade when data unsafe
- no execution with flags disabled
- user risk inputs unchanged
- RiskEngine required before execution
- no secrets in logs

Completion: run unit/integration tests, lint, type checks, security/secrets scan, backtest smoke suite, and Graphify update; report exact commands/results.
