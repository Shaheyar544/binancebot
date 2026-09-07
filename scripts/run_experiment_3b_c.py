"""Experiment 3B-C: Combined Breakeven (+1.0R) + Partial Take-Profit (+1.5R / 50%).

Tests combining causal breakeven ratchet (+1.0R trigger, entry + $0.50 buffer)
with 50% partial take-profit at +1.5R in strict experimental isolation.
Preserves the exact same 25,857 candles of 15M XAUUSDT data.
Evaluates against Phase 3A Baseline, Experiment 3B-A, and Experiment 3B-B.
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


def run_experiment_3b_c() -> dict[str, Any]:
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
        reason="Phase 3B Experiment C evaluation tier",
    )

    # Experiment C: Combined Breakeven + Partial TP
    exit_mgr = ExitManager(
        enable_breakeven=True,
        breakeven_r_multiple=Decimal("1.0"),
        breakeven_buffer=Decimal("0.50"),
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

    # Trades reaching targets
    r05_reached = [d for d in diags if d.max_r_reached >= Decimal("0.5")]
    r1_reached = [d for d in diags if d.max_r_reached >= Decimal("1.0")]
    r1_closed_loser = [d for d in r1_reached if d.net_pnl < Decimal("0.0")]
    r15_reached = [d for d in diags if d.max_r_reached >= Decimal("1.5")]
    r15_closed_loser = [d for d in r15_reached if d.net_pnl < Decimal("0.0")]
    r2_reached = [d for d in diags if d.max_r_reached >= Decimal("2.0")]

    # Positive MFE closing as loser
    pos_mfe_losers = [d for d in diags if d.net_pnl < Decimal("0.0") and d.mfe > Decimal("0.0")]

    # Activations
    be_trades = [d for d in diags if d.breakeven_activated]
    ptp_trades = [d for d in diags if d.partial_tp_taken]
    both_trades = [d for d in diags if d.breakeven_activated and d.partial_tp_taken]

    # Structural stop diagnostic
    sub_100 = [d for d in diags if d.initial_r < Decimal("1.00")]
    sub_050 = [d for d in diags if d.initial_r < Decimal("0.50")]
    sub_025 = [d for d in diags if d.initial_r < Decimal("0.25")]

    # Excursion metrics
    mfe_vals = [d.mfe for d in diags]
    sorted_mfe = sorted(mfe_vals)
    mfe_median = sorted_mfe[len(sorted_mfe) // 2] if sorted_mfe else Decimal("0.0")

    # Average holding duration
    durations_ms = [d.holding_duration_ms for d in diags if d.holding_duration_ms > 0]
    avg_duration_min = (
        round(Decimal(str(sum(durations_ms) / len(durations_ms))) / Decimal("60000"), 1)
        if durations_ms
        else Decimal("0.0")
    )

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

    # DCA Breakdown
    dca_trades = [d for d in diags if d.dca_count > 0]
    nodca_trades = [d for d in diags if d.dca_count == 0]

    # Exit reason breakdown
    exit_reasons: dict[str, int] = {}
    for d in diags:
        exit_reasons[d.exit_reason] = exit_reasons.get(d.exit_reason, 0) + 1

    total_diags_dec = Decimal(str(len(diags)))
    pct_05 = round(Decimal(str(len(r05_reached))) / total_diags_dec * Decimal("100.0"), 1)
    pct_10 = round(Decimal(str(len(r1_reached))) / total_diags_dec * Decimal("100.0"), 1)
    pct_15 = round(Decimal(str(len(r15_reached))) / total_diags_dec * Decimal("100.0"), 1)
    pct_20 = round(Decimal(str(len(r2_reached))) / total_diags_dec * Decimal("100.0"), 1)

    exp_c_data = {
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
        },
        "excursion": {
            "mfe_avg": str(result.mfe_avg),
            "mfe_median": str(round(mfe_median, 2)),
            "mae_avg": str(result.mae_avg),
            "mfe_r_avg": str(result.mfe_r_avg),
            "max_r_reached": str(result.max_r_reached),
            "realized_r_avg": str(result.r_realized_avg),
            "r_surrendered_avg": str(result.r_surrendered_avg),
            "mfe_realization_pct": str(result.mfe_realization_pct_winners),
            "giveback_pct": str(result.giveback_pct),
            "positive_mfe_closing_loser_pct": str(result.positive_mfe_closing_loser_pct) + "%",
            "pos_mfe_losers_count": len(pos_mfe_losers),
            "reach_05_r_pct": f"{pct_05}%",
            "reach_10_r_pct": f"{pct_10}%",
            "reach_15_r_pct": f"{pct_15}%",
            "reach_20_r_pct": f"{pct_20}%",
            "r1_reached_count": len(r1_reached),
            "r1_closed_as_loser_count": len(r1_closed_loser),
            "r15_reached_count": len(r15_reached),
            "r15_closed_as_loser_count": len(r15_closed_loser),
            "partial_tp_count": len(ptp_trades),
            "breakeven_activation_count": len(be_trades),
            "trades_receiving_both": len(both_trades),
        },
        "economic_impact": {
            "avg_trade_duration_minutes": str(avg_duration_min),
            "exit_reasons": exit_reasons,
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
        "structural_stop_diagnostic": {
            "count_initial_r_lt_1_00": len(sub_100),
            "count_initial_r_lt_0_50": len(sub_050),
            "count_initial_r_lt_0_25": len(sub_025),
            "sub_100_avg_mfe_r": (
                str(
                    round(
                        sum((d.mfe_r for d in sub_100), Decimal("0.0"))
                        / Decimal(str(len(sub_100))),
                        2,
                    )
                )
                if sub_100
                else "0.0"
            ),
            "sub_100_be_activations": len([d for d in sub_100 if d.breakeven_activated]),
            "sub_100_ptp_activations": len([d for d in sub_100 if d.partial_tp_taken]),
        },
    }

    # Load baseline, 3B-A, and 3B-B for 4-way comparative report
    with open("data/phase_3a_diagnostic_results.json", encoding="utf-8") as f:
        base_data = json.load(f)["overall"]

    with open("data/experiment_3b_a_results.json", encoding="utf-8") as f:
        exp_a_data = json.load(f)["experiment_3b_a"]

    with open("data/experiment_3b_b_results.json", encoding="utf-8") as f:
        exp_b_data = json.load(f)["experiment_3b_b_details"]["overall"]

    four_way_comparison = {
        "phase_3a_baseline": base_data,
        "experiment_3b_a_breakeven_only": exp_a_data,
        "experiment_3b_b_partial_tp_only": exp_b_data,
        "experiment_3b_c_combined": exp_c_data["overall"],
        "experiment_3b_c_details": exp_c_data,
    }

    return four_way_comparison


if __name__ == "__main__":
    results = run_experiment_3b_c()
    print(json.dumps(results, indent=2))
    with open("data/experiment_3b_c_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
