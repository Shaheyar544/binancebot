"""Run historical backtest and walk-forward validation on ingested Binance XAUUSDT data."""

import json
from decimal import Decimal
from pathlib import Path

from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.backtest.walk_forward import WalkForwardEngine
from src.config.settings import UserRiskConfig
from src.domain.enums import Timeframe
from src.domain.models import Candle


def load_candles(filepath: str = "data/xauusdt_15m.json") -> list[Candle]:
    """Load and parse saved candles from JSON."""
    with open(filepath, encoding="utf-8") as f:
        raw_list = json.load(f)

    candles: list[Candle] = []
    for item in raw_list:
        c = Candle(
            symbol=item["symbol"],
            timeframe=Timeframe(item["timeframe"]),
            open_time=item["open_time"],
            open=Decimal(str(item["open"])),
            high=Decimal(str(item["high"])),
            low=Decimal(str(item["low"])),
            close=Decimal(str(item["close"])),
            volume=Decimal(str(item["volume"])),
            close_time=item["close_time"],
            is_closed=item["is_closed"],
        )
        candles.append(c)

    candles.sort(key=lambda c: c.open_time)
    return candles


def main() -> None:
    data_path = Path("data/xauusdt_15m.json")
    if not data_path.exists():
        print("Data file not found. Please run scripts/fetch_historical_data.py first.")
        return

    candles = load_candles(str(data_path))
    print(f"Loaded {len(candles)} historical 15m candles.")
    start_ts = candles[0].open_time
    end_ts = candles[-1].close_time
    print(f"Range: timestamp {start_ts} to {end_ts}")

    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("2000.00"),
    )

    config = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        slippage_pct=Decimal("0.0001"),
        user_risk_config=user_risk,
    )

    print("\n" + "=" * 60)
    print("RUNNING FULL 9-MONTH HISTORICAL BACKTEST (25,857 CANDLES)")
    print("=" * 60)

    engine = BacktestEngine(config=config)
    result = engine.run(candles)

    print("\n--- BACKTEST PERFORMANCE SUMMARY ---")
    print(f"Total Trades:           {result.total_trades}")
    print(f"Winning Trades:         {result.winning_trades}")
    print(f"Losing Trades:          {result.losing_trades}")
    print(f"Win Rate:               {result.win_rate * 100:.2f}%")
    print(f"Gross Profit:           ${result.gross_profit:.2f}")
    print(f"Gross Loss:             ${result.gross_loss:.2f}")
    print(f"Net Profit:             ${result.net_profit:.2f}")
    print(f"Profit Factor:          {result.profit_factor:.2f}")
    print(f"Max Drawdown:           {result.max_drawdown_pct * 100:.2f}%")
    print(f"Total Fees Paid:        ${result.total_fees:.2f}")
    print(f"Total Funding Paid:     ${result.total_funding:.2f}")
    print(f"Liquidations:           {result.liquidations_count}")
    print(f"Trade Expectancy:       ${result.expectancy:.2f}")
    print(f"Sharpe Ratio:           {result.sharpe_ratio:.2f}")
    print(f"Sortino Ratio:          {result.sortino_ratio:.2f}")
    print(f"Calmar Ratio:           {result.calmar_ratio:.2f}")
    print(f"Consecutive Wins:       {result.consecutive_wins}")
    print(f"Consecutive Losses:     {result.consecutive_losses}")
    print(f"Max Exposure:           ${result.max_exposure:.2f}")
    print(f"Max Adds (DCA):         {result.max_adds}")
    print(f"Target Hit Rates:       {result.target_hit_rates}")

    print("\n" + "=" * 60)
    print("RUNNING WALK-FORWARD OUT-OF-SAMPLE VALIDATION")
    print("=" * 60)

    # 500 candles train (~5 days), 200 candles test (~2 days)
    wf_engine = WalkForwardEngine(
        config=config,
        train_candles_count=500,
        test_candles_count=200,
        step_candles_count=200,
    )
    wf_result = wf_engine.run(candles)

    print("\n--- WALK-FORWARD SUMMARY ---")
    print(f"Total Out-of-Sample Folds:  {wf_result.total_folds}")
    print(f"Profitable OOS Folds:       {wf_result.profitable_folds}")
    print(f"Stability Score:            {wf_result.stability_score * 100:.1f}%")
    print(f"Overall In-Sample Profit:   ${wf_result.overall_in_sample_profit:.2f}")
    print(f"Overall Out-of-Sample PnL:  ${wf_result.overall_out_of_sample_profit:.2f}")
    print(f"Strategy Robustness:        {'ROBUST' if wf_result.is_robust else 'ACCEPTABLE'}")


if __name__ == "__main__":
    main()
