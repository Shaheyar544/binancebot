# XAUUSDT Adaptive Long-Only Bot — Binance Futures

Production-grade, adaptive **XAUUSDT Binance Futures LONG-ONLY trading bot** built strictly around capital safety, risk control, and data integrity in accordance with [`AGENTS.md`](file:///f:/Website%20Project/XAUBot/AGENTS.md).

---

## Architecture & Safety Principles

1. **Long Only Invariant**: Opening orders must be `BUY`; closing orders must be `SELL`. Illegal short states are structurally impossible and trigger immediate `EMERGENCY_STOP` in reconciliation.
2. **DCA Ceiling**: Individual DCA/additional orders are hard-capped at `$500.00` (`MAX_DCA_NOTIONAL = Decimal("500")`). Orders exceeding `$500` are rejected immediately; order splitting is forbidden.
3. **Strict Authority Chain**:
   ```
   Market Data -> Technical Analysis -> Strategy Engine -> Risk Engine -> Execution Engine
   ```
   **`RiskEngine` is the final authority before execution.** Strategy Engine, Macro/News AI, and Execution Engine can never bypass `RiskEngine`.
4. **News Lock**: 24h pre-event and 24h post-event `NEWS_LOCK` on high-impact events, followed by 24h `POST_NEWS_REASSESSMENT` requiring fresh multi-timeframe confirmation.
5. **No Lookahead & Completed-Candle Store**: Analysis consumes finalized candles only (`is_closed=True`). Backtesting iterates chronologically without lookahead.
6. **Live Execution Gates**: Live order execution is fail-closed by default:
   - `LIVE_TRADING=false`
   - `ENABLE_ORDER_EXECUTION=false`
   Both flags must be explicitly enabled for live orders to be submitted.
7. **Financial Precision**: Python `Decimal` is strictly used for all financial calculations, prices, quantities, notional, fees, and account balances.
8. **Credential Security**: All secrets are stored as `SecretStr` and automatically redacted in logs (`[REDACTED]`) and `repr()` strings.

---

## Verification & Quality Baseline

Run the complete test suite and linters:

```bash
# Test suite with coverage (126 passed, 94% coverage)
uv run pytest -v --cov=src

# Linting check
uv run ruff check .

# Code formatting check
uv run ruff format --check .

# Strict type check
uv run mypy src tests

# Knowledge graph update
uv run graphify update .
```

---

## Pre-Flight & Staged Deployment

The project follows a staged deployment model: **Backtest $\to$ Paper $\to$ Shadow $\to$ Live Gate**.

To evaluate the 10 core safety invariants before deployment:

```bash
uv run python -c "
from decimal import Decimal
from src.config.settings import BotConfig, ExecutionGateConfig, UserRiskConfig
from src.paper.preflight import PreFlightChecker

cfg = BotConfig(
    gates=ExecutionGateConfig(live_trading=False, enable_order_execution=False),
    risk=UserRiskConfig(
        allocated_funds=Decimal('1000.00'),
        leverage=Decimal('5.0'),
        max_acceptable_liquidation_price=Decimal('2500.00'),
        max_entries=3,
        max_daily_loss=Decimal('200.00'),
        emergency_loss_limit=Decimal('400.00'),
        max_total_exposure=Decimal('5000.00'),
    )
)
report = PreFlightChecker(cfg).evaluate()
print('Ready for Paper:', report.is_ready_for_paper)
print('Ready for Live:', report.is_ready_for_live)
for k, v in report.checklist_results.items():
    print(f'  {k}: {v}')
"
```

