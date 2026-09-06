# Upstream Skills / Repositories

Keep third-party skills upstream rather than copying them into the project. Project-specific rules live under `.codex/skills/`.

## Graphify
https://github.com/Graphify-Labs/graphify

Use for codebase architecture mapping, relationships, path questions and incremental updates. Prefer the upstream Codex skill; do not create a competing local Graphify skill.

Recommended:
```bash
uv tool install --upgrade graphifyy
graphify .
graphify update .
```

## Superpowers
https://github.com/obra/superpowers

Use brainstorming, writing-plans, TDD, systematic-debugging, verification-before-completion, code review and subagent-driven development where supported. Follow the repo's current Codex installation instructions.

## emilkowalski/skills
https://github.com/emilkowalski/skills

Use only for dashboard/UI quality: `emil-design-eng`, `animate`, `review-animations`, `improve-animations`, `pick-ui-library`, `prototype`. UI skills must never alter trading/risk/execution behavior.

## Project-local skills
- xau-binance-integration
- xau-market-analysis
- xau-strategy
- xau-risk
- xau-macro-news
- xau-backtesting
- xau-execution
- xau-dashboard
- xau-qa
