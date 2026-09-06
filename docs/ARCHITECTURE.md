# Architecture

## Layers
- **Exchange Adapter:** Binance REST/WebSocket, exchange metadata, account state, orders.
- **Market Data:** canonical completed 15M/1H/4H/1D candles plus mark/index/funding/OI/order-book snapshots.
- **Analysis:** structure, trend, momentum, volume, S/R, volatility, regime.
- **Macro/News Intelligence:** event calendars/news; intelligence only; never execution.
- **Strategy Engine:** multi-timeframe candidate decision and explanation.
- **Risk Engine:** hard gate for sizing, liquidation, exposure, daily loss, DCA cap, event lock, volatility and data quality.
- **Execution Engine:** only layer allowed to submit orders.
- **Reconciliation:** startup/reconnect/periodic account and order reconciliation.
- **Persistence:** SQLite V1 with immutable decision snapshots.
- **Dashboard:** monitoring/control surface that cannot bypass RiskEngine.

## Dependency direction
`exchange -> market_data -> analysis -> strategy -> risk -> execution`
`macro/news -> strategy`
`persistence <- all stateful layers`
`dashboard -> API -> state`

No UI code in trading logic. No execution import inside Strategy or AI modules.

## Suggested structure
```text
xau-adaptive-bot/
  AGENTS.md
  README.md
  pyproject.toml
  .env.example
  .gitignore
  config/
  docs/
  src/
    main.py
    config/
    exchange/
    market_data/
    analysis/
    strategy/
    macro/
    risk/
    execution/
    portfolio/
    storage/
    monitoring/
    dashboard/
  tests/
  backtest/
  scripts/
  graphify-out/
```
