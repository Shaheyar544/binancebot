# Start Here

## 1. Install upstream skills

### Graphify
```bash
uv tool install --upgrade graphifyy
graphify .
```

### Superpowers
Follow the current Codex installation instructions in the upstream `obra/superpowers` repository.

### UI skills
For dashboard work only:
```bash
npx skills@latest add emilkowalski/skills
```

## 2. Copy this pack into the bot repository

Keep:
- `AGENTS.md`
- `.codex/skills/`
- `docs/`
- `tests/skill-pressure/`

Do not create a second local Graphify skill if the upstream Graphify skill is installed.

## 3. First prompt

Use `docs/MASTER_BUILD_PROMPT.md` together with `docs/prompts/00_BOOTSTRAP.md`.

## 4. Then run prompts in order

`01_MARKET_DATA` -> `02_STRATEGY` -> `03_RISK` -> `06_BACKTEST` -> `05_EXECUTION` -> `04_MACRO_NEWS` -> `07_DASHBOARD` -> `08_PAPER_TO_LIVE` -> `09_AUDIT`.

Execution intentionally comes after Risk and Backtest foundations.
