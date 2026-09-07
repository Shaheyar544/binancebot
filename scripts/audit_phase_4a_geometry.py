"""Phase 4A: Dynamic Structural Stop & Risk Geometry Remediation Audit Script.

Compares:
1. Phase 3C Baseline (Clean Uncorrupted ExitManager with Breakeven only)
2. Phase 4A Remediated (Structural Stop Relocation + 0.5 * ATR Noise Floor)

Evaluates:
- Distribution of setups and micro-stops ($R < $1.00 and $R < 0.5 * ATR)
- Configured ($10.00) vs Theoretical vs Actual Dollar Risk
- Full backtest performance across 25,857 candles
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


def run_phase_4a_audit() -> dict[str, Any]:
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
        reason="Phase 4A Audit evaluation tier",
    )

    # 1. Setup scan across all 25,857 candles under Remediated EntryOrchestrator
    orchestrator = EntryOrchestrator()
    remediated_setups = []
    for i in range(20, len(candles)):
        recent = candles[max(0, i - 1000) : i + 1]
        c = recent[-1]
        analysis = TimeframeAnalyzer.analyze_timeframe(recent, Timeframe.M15)
        sup, res = orchestrator.identify_levels(recent)
        setup = orchestrator.evaluate_setups(
            recent,
            analysis.ema_20,
            analysis.ema_50,
            sup,
            res,
            atr=analysis.atr,
        )
        if setup is not None:
            init_r = c.close - setup.stop_loss_ref
            atr = analysis.atr
            ratio = (init_r / atr) if atr and atr > Decimal("0.0") else Decimal("0.0")
            r_over_price = init_r / c.close
            remediated_setups.append(
                {
                    "family": setup.family.value,
                    "initial_r": float(init_r),
                    "atr": float(atr) if atr else 0.0,
                    "r_over_atr": float(ratio),
                    "r_over_price": float(r_over_price),
                }
            )

    tot_setups = len(remediated_setups)
    r_vals = [s["initial_r"] for s in remediated_setups]
    r_over_atr = [s["r_over_atr"] for s in remediated_setups]

    geometry_summary = {
        "total_setups": tot_setups,
        "min_initial_r": min(r_vals) if r_vals else 0.0,
        "max_initial_r": max(r_vals) if r_vals else 0.0,
        "median_initial_r": sorted(r_vals)[tot_setups // 2] if tot_setups else 0.0,
        "count_r_lt_1_00": sum(1 for r in r_vals if r < 1.0),
        "count_r_lt_0_50_atr": sum(1 for r in r_over_atr if r < 0.50),
        "count_r_lt_0_25_atr": sum(1 for r in r_over_atr if r < 0.25),
        "median_r_over_atr": sorted(r_over_atr)[tot_setups // 2] if tot_setups else 0.0,
    }

    # 2. Run Backtest with Breakeven Only (Phase 4A Remediated)
    # Compare with clean Phase 3C metrics
    print(f"Running Phase 4A Remediated Backtest across {len(candles)} candles...")
    exit_mgr = ExitManager(enable_breakeven=True, enable_partial_tp=False)
    engine = BacktestEngine(config=config, exit_manager=exit_mgr, estimator=estimator)
    res = engine.run(candles)
    diags: list[PerTradeDiagnostic] = res.diagnostics

    # Sizing audit
    sizing_records = []
    for d in diags:
        sizing_records.append(
            {
                "trade_id": d.trade_id,
                "initial_r": float(d.initial_r),
                "r_over_atr": float(d.r_over_atr),
                "configured_risk": float(d.configured_risk),
                "theoretical_risk": float(d.theoretical_risk),
                "actual_risk": float(d.actual_risk),
                "actual_risk_pct": float(d.actual_risk_pct),
            }
        )

    tot_trades = len(sizing_records)
    act_risks = sorted(s["actual_risk"] for s in sizing_records)
    r_over_atrs = sorted(s["r_over_atr"] for s in sizing_records)

    sizing_summary = {
        "total_trades": tot_trades,
        "min_actual_risk": min(act_risks) if act_risks else 0.0,
        "max_actual_risk": max(act_risks) if act_risks else 0.0,
        "median_actual_risk": act_risks[tot_trades // 2] if tot_trades else 0.0,
        "count_actual_risk_lt_1_dollar": sum(1 for r in act_risks if r < 1.0),
        "count_actual_risk_lt_5_dollars": sum(1 for r in act_risks if r < 5.0),
        "pct_actual_risk_lt_5_dollars": (
            f"{round(sum(1 for r in act_risks if r < 5.0) / tot_trades * 100, 2)}%"
            if tot_trades
            else "0%"
        ),
        "min_r_over_atr": min(r_over_atrs) if r_over_atrs else 0.0,
        "median_r_over_atr": r_over_atrs[tot_trades // 2] if tot_trades else 0.0,
    }

    # Performance summary
    perf_summary = {
        "total_trades": res.total_trades,
        "winning_trades": res.winning_trades,
        "losing_trades": res.losing_trades,
        "win_rate": float(res.win_rate),
        "gross_profit": float(res.gross_profit),
        "gross_loss": float(res.gross_loss),
        "net_profit": float(res.net_profit),
        "profit_factor": float(res.profit_factor),
        "max_drawdown_pct": float(res.max_drawdown_pct),
        "total_fees": float(res.total_fees),
        "total_maker_fees": float(res.total_maker_fees),
        "total_taker_fees": float(res.total_taker_fees),
        "total_funding": float(res.total_funding),
        "mfe_avg": float(res.mfe_avg),
        "mfe_median": float(res.mfe_median),
        "mae_avg": float(res.mae_avg),
        "mfe_r_avg": float(res.mfe_r_avg),
        "max_r_reached": float(res.max_r_reached),
        "r_realized_avg": float(res.r_realized_avg),
        "r_surrendered_avg": float(res.r_surrendered_avg),
        "mfe_realization_pct_winners": float(res.mfe_realization_pct_winners),
        "giveback_pct": float(res.giveback_pct),
        "positive_mfe_closing_loser_pct": float(res.positive_mfe_closing_loser_pct),
        "r_target_hit_rates": {k: float(v) for k, v in res.r_target_hit_rates.items()},
        "setup_family_performance": {
            k: {inner_k: float(inner_v) for inner_k, inner_v in v.items()}
            for k, v in res.setup_family_performance.items()
        },
        "regime_performance": {
            k: {inner_k: float(inner_v) for inner_k, inner_v in v.items()}
            for k, v in res.regime_performance.items()
        },
    }

    report = {
        "geometry_summary": geometry_summary,
        "sizing_summary": sizing_summary,
        "perf_summary": perf_summary,
    }

    with open("phase_4a_results.json", "w") as f:
        json.dump(report, f, indent=2)

    print("Phase 4A Audit Complete. Results saved to phase_4a_results.json")
    return report


if __name__ == "__main__":
    run_phase_4a_audit()
