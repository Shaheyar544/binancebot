"""Experiment 3B-B: Partial Take-Profit (+1.5R / 50%) Only.

Tests 50% partial take-profit at +1.5R in strict experimental isolation.
Breakeven is explicitly disabled. No entry/weight/regime changes.
Evaluates against Phase 3A baseline and Experiment 3B-A.
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


def run_experiment_3b_b() -> dict[str, Any]:
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
        reason="Phase 3B Experiment B evaluation tier",
    )

    # Experiment B: Partial TP ONLY (+1.5R / 50%), NO Breakeven
    exit_mgr = ExitManager(
        enable_breakeven=False,
        enable_partial_tp=True,
        partial_tp_ratio=Decimal("1.5"),
        partial_tp_pct=Decimal("50.0"),
    )

    engine = BacktestEngine(config=config, exit_manager=exit_mgr, estimator=estimator)
    result = engine.run(candles)
    diags: list[PerTradeDiagnostic] = result.diagnostics

    r_list = [d.realized_r for d in diags]
    sorted_r = sorted(r_list)
    median_r = sorted_r[len(sorted_r) // 2] if sorted_r else Decimal("0.0")
    avg_r = sum(r_list, Decimal("0.0")) / Decimal(str(len(r_list))) if r_list else Decimal("0.0")

    # Trades reaching >= 1.0R and >= 1.5R
    r1_reached = [d for d in diags if d.max_r_reached >= Decimal("1.0")]
    r1_closed_loser = [d for d in r1_reached if d.net_pnl < Decimal("0.0")]

    r15_reached = [d for d in diags if d.max_r_reached >= Decimal("1.5")]
    r15_closed_loser = [d for d in r15_reached if d.net_pnl < Decimal("0.0")]

    # Positive MFE closing as loser
    pos_mfe_losers = [d for d in diags if d.net_pnl < Decimal("0.0") and d.mfe > Decimal("0.0")]

    # Partial TP trigger stats
    ptp_trades = [d for d in diags if d.partial_tp_taken]

    # DCA breakdown
    dca_trades = [d for d in diags if d.dca_count > 0]
    nodca_trades = [d for d in diags if d.dca_count == 0]

    def _subset_metrics(trades_subset: list[PerTradeDiagnostic]) -> dict[str, Any]:
        count = len(trades_subset)
        if count == 0:
            return {"count": 0}
        wins = [d for d in trades_subset if d.net_pnl > Decimal("0.0")]
        losses = [d for d in trades_subset if d.net_pnl < Decimal("0.0")]
        gross_win = sum((d.gross_pnl for d in wins), Decimal("0.0"))
        gross_loss = abs(sum((d.gross_pnl for d in losses), Decimal("0.0")))
        net = sum((d.net_pnl for d in trades_subset), Decimal("0.0"))
        pf = round(gross_win / gross_loss, 2) if gross_loss > Decimal("0.0") else Decimal("0.0")
        sub_r = [d.realized_r for d in trades_subset]
        win_pct = round(Decimal(str(len(wins))) / Decimal(str(count)) * Decimal("100.0"), 2)
        return {
            "count": count,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": f"{win_pct}%",
            "gross_profit": str(round(gross_win, 2)),
            "gross_loss": str(round(gross_loss, 2)),
            "net_profit": str(round(net, 2)),
            "profit_factor": str(pf),
            "avg_r": str(round(sum(sub_r, Decimal("0.0")) / Decimal(str(count)), 2)),
        }

    # Exit reason distribution
    exit_reasons: dict[str, int] = {}
    for d in diags:
        exit_reasons[d.exit_reason] = exit_reasons.get(d.exit_reason, 0) + 1

    r_targets = result.r_target_hit_rates
    exp_b_data = {
        "overall": {
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
            "partial_tp_executed_count": len(ptp_trades),
        },
        "mfe_mae": {
            "mfe_avg": str(result.mfe_avg),
            "mfe_median": str(result.mfe_median),
            "mae_avg": str(result.mae_avg),
            "mfe_r_avg": str(result.mfe_r_avg),
            "max_r_reached": str(result.max_r_reached),
            "r_realized_avg": str(result.r_realized_avg),
            "r_surrendered_avg": str(result.r_surrendered_avg),
            "mfe_realization_pct_winners": str(result.mfe_realization_pct_winners),
            "giveback_pct": str(result.giveback_pct),
            "positive_mfe_closing_loser_pct": str(result.positive_mfe_closing_loser_pct) + "%",
            "pos_mfe_losers_count": len(pos_mfe_losers),
        },
        "r_target_reach": {
            "0.5R": str(round(r_targets.get("0.5R", Decimal("0.0")) * 100, 1)) + "%",
            "1.0R": str(round(r_targets.get("1.0R", Decimal("0.0")) * 100, 1)) + "%",
            "1.5R": str(round(r_targets.get("1.5R", Decimal("0.0")) * 100, 1)) + "%",
            "2.0R": str(round(r_targets.get("2.0R", Decimal("0.0")) * 100, 1)) + "%",
            "r1_reached_count": len(r1_reached),
            "r1_closed_as_loser_count": len(r1_closed_loser),
            "r15_reached_count": len(r15_reached),
            "r15_closed_as_loser_count": len(r15_closed_loser),
        },
        "segments": {
            "dca": _subset_metrics(dca_trades),
            "no_dca": _subset_metrics(nodca_trades),
            "score_buckets": {
                k: {sk: str(sv) for sk, sv in v.items()}
                for k, v in result.score_bucket_performance.items()
            },
            "setup_families": {
                k: {sk: str(sv) for sk, sv in v.items()}
                for k, v in result.setup_family_performance.items()
            },
            "regimes": {
                k: {sk: str(sv) for sk, sv in v.items()}
                for k, v in result.regime_performance.items()
            },
        },
        "exit_reasons": exit_reasons,
    }

    # Load Phase 3A Baseline and Experiment 3B-A for 3-way comparative report
    with open("data/phase_3a_diagnostic_results.json", encoding="utf-8") as f:
        base_data = json.load(f)

    with open("data/experiment_3b_a_results.json", encoding="utf-8") as f:
        exp_a_data = json.load(f)["experiment_3b_a"]

    three_way_comparison = {
        "phase_3a_baseline": base_data["overall"],
        "experiment_3b_a_breakeven_only": exp_a_data,
        "experiment_3b_b_partial_tp_only": exp_b_data["overall"],
        "experiment_3b_b_details": exp_b_data,
    }

    return three_way_comparison


if __name__ == "__main__":
    results = run_experiment_3b_b()
    print(json.dumps(results, indent=2))
    with open("data/experiment_3b_b_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
