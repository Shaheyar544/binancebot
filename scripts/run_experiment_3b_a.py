"""Experiment 3B-A: Causal +1.0R Breakeven Protection Only.

Tests breakeven ratchet (+1.0R trigger, entry + $0.50 buffer) in strict isolation
against the untouched Phase 3A baseline. No partial TP, no regime filters, no score changes.
"""

import json
from decimal import Decimal
from typing import Any

from scripts.diagnose_phase_3a import load_candles
from src.backtest.engine import BacktestEngine
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    LiquidationModelPolicy,
    PerTradeDiagnostic,
)
from src.config.settings import UserRiskConfig
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager


def run_experiment_3b_a() -> dict[str, Any]:
    candles = load_candles()
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("2000.00"),
    )

    policy = BacktestExecutionPolicy(liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL)
    config = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        slippage_pct=Decimal("0.0001"),
        user_risk_config=user_risk,
        execution_policy=policy,
    )

    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
        reason="Phase 3B Experiment A evaluation tier",
    )

    # Experiment A: Breakeven ONLY, NO partial TP
    exit_mgr = ExitManager(
        enable_breakeven=True,
        breakeven_r_multiple=Decimal("1.0"),
        breakeven_buffer=Decimal("0.50"),
        enable_partial_tp=False,
    )

    engine = BacktestEngine(config=config, exit_manager=exit_mgr, estimator=estimator)
    result = engine.run(candles)
    diags: list[PerTradeDiagnostic] = result.diagnostics

    r_list = [d.realized_r for d in diags]
    sorted_r = sorted(r_list)
    median_r = sorted_r[len(sorted_r) // 2] if sorted_r else Decimal("0.0")
    avg_r = sum(r_list, Decimal("0.0")) / Decimal(str(len(r_list))) if r_list else Decimal("0.0")

    # Trades reaching >= 1.0R
    r1_reached = [d for d in diags if d.max_r_reached >= Decimal("1.0")]
    r1_closed_loser = [d for d in r1_reached if d.net_pnl < Decimal("0.0")]
    r1_not_realized = [d for d in r1_reached if d.realized_r < Decimal("1.0")]

    # Positive MFE closing as loser
    pos_mfe_losers = [d for d in diags if d.net_pnl < Decimal("0.0") and d.mfe > Decimal("0.0")]

    exp_data = {
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "win_rate": str(round(result.win_rate * 100, 2)) + "%",
        "gross_profit": str(round(result.gross_profit, 2)),
        "gross_loss": str(round(result.gross_loss, 2)),
        "net_profit": str(round(result.net_profit, 2)),
        "profit_factor": str(result.profit_factor),
        "total_fees": str(round(result.total_fees, 2)),
        "total_funding": str(round(result.total_funding, 2)),
        "max_drawdown_pct": str(round(result.max_drawdown_pct * 100, 2)) + "%",
        "avg_r": str(round(avg_r, 2)),
        "median_r": str(round(median_r, 2)),
        "r1_reached_count": len(r1_reached),
        "r1_closed_as_loser_count": len(r1_closed_loser),
        "r1_closed_as_loser_pct": (
            str(
                round(
                    Decimal(str(len(r1_closed_loser)))
                    / Decimal(str(len(r1_reached)))
                    * Decimal("100.0"),
                    2,
                )
            )
            + "%"
            if r1_reached
            else "0.0%"
        ),
        "r1_not_realized_count": len(r1_not_realized),
        "pos_mfe_losers_count": len(pos_mfe_losers),
        "positive_mfe_closing_loser_pct": str(result.positive_mfe_closing_loser_pct) + "%",
    }

    # Load baseline for comparison
    with open("data/phase_3a_diagnostic_results.json", encoding="utf-8") as f:
        base_data = json.load(f)

    comparison = {
        "baseline_phase_3a": base_data["overall"],
        "baseline_r1_losers": base_data["r_target_reach"]["r1_closed_as_loser_count"],
        "baseline_r1_losers_pct": base_data["r_target_reach"]["r1_closed_as_loser_pct"],
        "baseline_pos_mfe_losers": base_data["mfe_mae"]["pos_mfe_losers_count"],
        "experiment_3b_a": exp_data,
    }

    return comparison


if __name__ == "__main__":
    comp = run_experiment_3b_a()
    print(json.dumps(comp, indent=2))
    with open("data/experiment_3b_a_results.json", "w", encoding="utf-8") as f:
        json.dump(comp, f, indent=2)
