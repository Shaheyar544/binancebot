# Prompt 00 — Bootstrap

Build the XAUUSDT Adaptive Long-Only Binance Futures Bot from `AGENTS.md`, `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, and `docs/IMPLEMENTATION_PLAN.md`.

First inspect the repository and installed skills. If Graphify exists, query it before broad source browsing. Use the Superpowers workflow for design/plan/TDD/debugging/verification where available.

Do not write trading logic yet. Establish the Python project, typed configuration, domain models, test harness, lint/type tooling, safe `.env.example`, logging, SQLite foundation, and disabled-live execution gates.

Before coding, produce a concise implementation plan with exact files and tests. Implement Phase 0 and Phase 1 only. Do not invent missing exchange facts; mark them as TODOs requiring official Binance documentation.

Acceptance: safe startup; required risk settings validated; incompatible liquidation rejected; DCA > $500 rejected; live execution impossible with default flags; tests pass; no secrets committed; Graphify updated.
