# XAUUSDT Adaptive Bot — Agent Build Pack

This pack contains the project-local specification, prompts and Codex skills for building the XAUUSDT long-only Binance Futures bot.

Start with `AGENTS.md`, then `docs/PROJECT_SPEC.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/prompts/00_BOOTSTRAP.md`, and `.codex/skills/`.

Third-party skills are intentionally not copied. Install/pin Graphify, Superpowers and emilkowalski skills from upstream; see `docs/UPSTREAM_SKILLS.md`.

Build order: Bootstrap -> Market Data -> Analysis -> Strategy -> Risk -> Backtest -> Execution/Reconciliation -> Macro/News -> Dashboard -> Paper/Shadow -> Live Gate.
