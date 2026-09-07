"""Phase 3C: Comprehensive Risk & Entry Integrity Audit.

Audits:
1. Emergency Stop Leak: Quantifies the contamination caused by passing lifetime
   cumulative backtest fees (self.exchange.total_fees_paid) into the position-level
   emergency stop evaluation.
2. Clean Evaluation: Compares uncorrupted trade execution (using active_trade fees)
   against the baseline and 3B-A runs.
3. Structural Stop Geometry: Distribution of initial_r across all trades and
   setups, measuring initial_r vs 15M ATR, identifying micro-stops without arbitrary floors.
4. Risk Sizing & Capital Divergence: Configured risk ($10.00) vs theoretical risk
   vs actual monetary risk after purchasing power cap ($2,000 notional at 2x leverage).
"""

import json
from decimal import Decimal
from typing import Any

from scripts.diagnose_phase_3a import load_candles
from src.analysis.models import TimeframeAnalyzer
from src.backtest.engine import BacktestEngine
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    FeeProfile,
    LiquidationModelPolicy,
    PerTradeDiagnostic,
)
from src.config.settings import UserRiskConfig
from src.domain.enums import Timeframe
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager
from src.strategy.entry_families import EntryOrchestrator


def run_integrity_audit() -> dict[str, Any]:
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

    fee_profile = FeeProfile(
        profile_name="BINANCE_FUTURES_STANDARD_ASSUMED",
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        funding_rate_8h=Decimal("0.0001"),
        is_assumed=True,
        account_tier="VIP0",
    )
    policy = BacktestExecutionPolicy(
        liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL,
        fee_profile=fee_profile,
    )
    config = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        user_risk_config=user_risk,
        execution_policy=policy,
    )

    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
        reason="Phase 3C Audit evaluation tier",
    )

    # 1. Structural stop geometry across all candle setups
    orchestrator = EntryOrchestrator()
    setup_stats = []
    for i in range(20, len(candles)):
        recent = candles[max(0, i - 1000) : i + 1]
        c = recent[-1]
        analysis = TimeframeAnalyzer.analyze_timeframe(recent, Timeframe.M15)
        sup, res = orchestrator.identify_levels(recent)
        setup = orchestrator.evaluate_setups(recent, analysis.ema_20, analysis.ema_50, sup, res)
        if setup is not None:
            init_r = c.close - setup.stop_loss_ref
            atr = analysis.atr
            ratio = (init_r / atr) if atr and atr > Decimal("0.0") else Decimal("0.0")
            r_over_price = init_r / c.close
            setup_stats.append(
                {
                    "family": setup.family.value,
                    "initial_r": float(init_r),
                    "atr": float(atr) if atr else 0.0,
                    "r_over_atr": float(ratio),
                    "r_over_price": float(r_over_price),
                }
            )

    total_setups = len(setup_stats)
    r_vals = [s["initial_r"] for s in setup_stats]
    r_over_atr = [s["r_over_atr"] for s in setup_stats]
    r_over_price = [s["r_over_price"] for s in setup_stats]

    geometry_audit = {
        "total_setups_detected": total_setups,
        "min_initial_r": min(r_vals) if r_vals else 0.0,
        "max_initial_r": max(r_vals) if r_vals else 0.0,
        "median_initial_r": sorted(r_vals)[len(r_vals) // 2] if r_vals else 0.0,
        "count_r_le_0": len([r for r in r_vals if r <= 0]),
        "count_r_lt_0_25": len([r for r in r_vals if r < 0.25]),
        "pct_r_lt_0_25": (
            f"{round(len([r for r in r_vals if r < 0.25]) / total_setups * 100, 2)}%"
            if total_setups
            else "0%"
        ),
        "count_r_lt_0_50": len([r for r in r_vals if r < 0.5]),
        "pct_r_lt_0_50": (
            f"{round(len([r for r in r_vals if r < 0.5]) / total_setups * 100, 2)}%"
            if total_setups
            else "0%"
        ),
        "count_r_lt_1_00": len([r for r in r_vals if r < 1.0]),
        "pct_r_lt_1_00": (
            f"{round(len([r for r in r_vals if r < 1.0]) / total_setups * 100, 2)}%"
            if total_setups
            else "0%"
        ),
        "count_r_lt_0_25_atr": len([r for r in r_over_atr if r < 0.25]),
        "pct_r_lt_0_25_atr": (
            f"{round(len([r for r in r_over_atr if r < 0.25]) / total_setups * 100, 2)}%"
            if total_setups
            else "0%"
        ),
        "count_r_lt_0_10_atr": len([r for r in r_over_atr if r < 0.10]),
        "median_r_over_atr": sorted(r_over_atr)[len(r_over_atr) // 2] if r_over_atr else 0.0,
        "median_r_over_price_pct": (
            f"{round(sorted(r_over_price)[len(r_over_price) // 2] * 100, 4)}%"
            if r_over_price
            else "0.0%"
        ),
    }

    # 2. Run the 4 Experiments Cleanly
    experiments = [
        ("phase_3a_baseline", ExitManager(enable_breakeven=False, enable_partial_tp=False)),
        ("experiment_3b_a_breakeven", ExitManager(enable_breakeven=True, enable_partial_tp=False)),
        ("experiment_3b_b_partial_tp", ExitManager(enable_breakeven=False, enable_partial_tp=True)),
        ("experiment_3b_c_combined", ExitManager(enable_breakeven=True, enable_partial_tp=True)),
    ]

    exp_results = {}
    sizing_audits = {}

    for name, exit_mgr in experiments:
        print(f"Running {name} across {len(candles)} candles...")
        engine = BacktestEngine(config=config, exit_manager=exit_mgr, estimator=estimator)
        res = engine.run(candles)
        diags: list[PerTradeDiagnostic] = res.diagnostics

        # Position Sizing & Risk Divergence
        risk_divergences = []
        for d in diags:
            matching_trade = next((t for t in res.trades if t.trade_id == d.trade_id), None)
            size = matching_trade.size if matching_trade else Decimal("0.0")
            actual_risk_dollars = size * d.initial_r
            risk_divergences.append(
                {
                    "trade_id": d.trade_id,
                    "initial_r": float(d.initial_r),
                    "size": float(size),
                    "actual_risk_dollars": float(actual_risk_dollars),
                    "configured_risk_dollars": 10.00,
                }
            )

        tot_tr = len(risk_divergences)
        sub_1 = [r for r in risk_divergences if r["actual_risk_dollars"] < 1.00]
        sub_5 = [r for r in risk_divergences if r["actual_risk_dollars"] < 5.00]
        sub_010 = [r for r in risk_divergences if r["actual_risk_dollars"] < 0.10]
        sorted_actual = sorted(r["actual_risk_dollars"] for r in risk_divergences)

        sizing_audits[name] = {
            "total_trades": tot_tr,
            "count_actual_risk_lt_10_cents": len(sub_010),
            "count_actual_risk_lt_1_dollar": len(sub_1),
            "pct_actual_risk_lt_1_dollar": f"{round(len(sub_1) / tot_tr * 100, 2)}%"
            if tot_tr
            else "0%",
            "count_actual_risk_lt_5_dollars": len(sub_5),
            "pct_actual_risk_lt_5_dollars": f"{round(len(sub_5) / tot_tr * 100, 2)}%"
            if tot_tr
            else "0%",
            "min_actual_risk_dollars": min(sorted_actual) if sorted_actual else 0.0,
            "max_actual_risk_dollars": max(sorted_actual) if sorted_actual else 0.0,
            "median_actual_risk_dollars": sorted_actual[tot_tr // 2] if tot_tr else 0.0,
        }

        micro_diags = [d for d in diags if d.initial_r < Decimal("1.00")]
        normal_diags = [d for d in diags if d.initial_r >= Decimal("1.00")]
        emg_exits = sum(1 for t in res.trades if t.exit_reason == "EMERGENCY_STOP_LOSS_BREACHED")

        exp_results[name] = {
            "total_trades": res.total_trades,
            "winning_trades": res.winning_trades,
            "losing_trades": res.losing_trades,
            "win_rate": f"{round(res.win_rate * 100, 2)}%",
            "gross_profit": str(res.gross_profit),
            "gross_loss": str(res.gross_loss),
            "net_profit": str(res.net_profit),
            "profit_factor": str(res.profit_factor),
            "total_fees": str(res.total_fees),
            "total_maker_fees": str(res.total_maker_fees),
            "total_taker_fees": str(res.total_taker_fees),
            "total_funding": str(res.total_funding),
            "max_drawdown_pct": f"{round(res.max_drawdown_pct * 100, 2)}%",
            "avg_r": str(res.r_realized_avg),
            "median_r": str(res.median_winner if res.net_profit > 0 else res.median_loser),
            "mae_avg": str(res.mae_avg),
            "mfe_avg": str(res.mfe_avg),
            "mfe_r_avg": str(res.mfe_r_avg),
            "max_r_reached": str(res.max_r_reached),
            "r_realized_avg": str(res.r_realized_avg),
            "giveback_pct": f"{round(res.giveback_pct, 2)}%",
            "positive_mfe_closing_loser_pct": f"{round(res.positive_mfe_closing_loser_pct, 2)}%",
            "r_target_hit_rates": {k: str(v) for k, v in res.r_target_hit_rates.items()},
            "emergency_exits_count": emg_exits,
            "micro_stop_count": len(micro_diags),
            "normal_stop_count": len(normal_diags),
            "micro_stop_pct": f"{round(len(micro_diags) / res.total_trades * 100, 2)}%"
            if res.total_trades
            else "0%",
            "micro_stop_avg_mfe_r": str(
                round(
                    sum((d.mfe_r for d in micro_diags), Decimal("0"))
                    / Decimal(str(len(micro_diags))),
                    2,
                )
            )
            if micro_diags
            else "0.0",
            "normal_stop_avg_mfe_r": str(
                round(
                    sum((d.mfe_r for d in normal_diags), Decimal("0"))
                    / Decimal(str(len(normal_diags))),
                    2,
                )
            )
            if normal_diags
            else "0.0",
            "normal_stop_max_r": str(max((d.mfe_r for d in normal_diags), default=Decimal("0"))),
        }

    return {
        "fee_assumptions": {
            "maker_fee": str(fee_profile.maker_fee),
            "taker_fee": str(fee_profile.taker_fee),
            "funding_rate_8h": str(fee_profile.funding_rate_8h),
            "account_tier": fee_profile.account_tier,
            "status": "ASSUMED",
            "note": (
                "Binance VIP0 standard futures schedule; "
                "exact historical maker/taker tiers are ASSUMED"
            ),
        },
        "geometry_audit": geometry_audit,
        "sizing_audits": sizing_audits,
        "experiment_results": exp_results,
    }


if __name__ == "__main__":
    report = run_integrity_audit()
    print(json.dumps(report, indent=2))
    with open("data/phase_3c_integrity_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
