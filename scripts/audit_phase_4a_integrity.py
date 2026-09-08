import json
from decimal import Decimal
from typing import Any

from scripts.diagnose_phase_3a import load_candles
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.config.settings import UserRiskConfig
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager, StrategyEngine


def run_full_audit() -> dict[str, Any]:
    candles = load_candles()
    risk_config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
        max_entries=3,
        risk_per_trade_pct=Decimal("1.0"),
    )
    cfg = BacktestConfig(user_risk_config=risk_config)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2000.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    strat_engine = StrategyEngine(min_entry_score=85)
    exit_mgr = ExitManager()
    engine = BacktestEngine(
        config=cfg,
        strategy_engine=strat_engine,
        exit_manager=exit_mgr,
        estimator=estimator,
    )
    res = engine.run(candles)

    # 1. Reconcile stop implementation and micro-stops across all trades
    diag_map = {d.trade_id: d for d in res.diagnostics}
    trades = res.trades

    micro_stops = {
        "initial_r_lt_0_25": 0,
        "initial_r_lt_0_50": 0,
        "initial_r_lt_1_00": 0,
        "r_over_atr_lt_0_1": 0,
        "r_over_atr_lt_0_2": 0,
        "r_over_atr_lt_0_3": 0,
        "r_over_atr_lt_0_5": 0,
    }

    micro_stops_by_family: dict[str, dict[str, int]] = {}
    micro_stops_by_regime: dict[str, dict[str, int]] = {}

    all_trade_records = []
    dca_trades = []
    non_dca_trades = []

    for t in trades:
        d = diag_map.get(t.trade_id)
        if not d:
            continue

        r = d.initial_r
        atr = d.atr_at_entry
        r_over_atr = r / atr if atr > Decimal("0.0") else Decimal("0.0")

        if r < Decimal("0.25"):
            micro_stops["initial_r_lt_0_25"] += 1
        if r < Decimal("0.50"):
            micro_stops["initial_r_lt_0_50"] += 1
        if r < Decimal("1.00"):
            micro_stops["initial_r_lt_0_1"] = micro_stops.get("initial_r_lt_0_1", 0)
            micro_stops["initial_r_lt_1_00"] += 1

        if r_over_atr < Decimal("0.10"):
            micro_stops["r_over_atr_lt_0_1"] += 1
        if r_over_atr < Decimal("0.20"):
            micro_stops["r_over_atr_lt_0_2"] += 1
        if r_over_atr < Decimal("0.30"):
            micro_stops["r_over_atr_lt_0_3"] += 1
        if r_over_atr < Decimal("0.50"):
            micro_stops["r_over_atr_lt_0_5"] += 1

        fam = d.entry_family
        reg = d.regime

        micro_stops_by_family.setdefault(
            fam, {"count_r_lt_1_00": 0, "count_r_over_atr_lt_0_5": 0, "total": 0}
        )
        micro_stops_by_family[fam]["total"] += 1
        if r < Decimal("1.00"):
            micro_stops_by_family[fam]["count_r_lt_1_00"] += 1
        if r_over_atr < Decimal("0.50"):
            micro_stops_by_family[fam]["count_r_over_atr_lt_0_5"] += 1

        micro_stops_by_regime.setdefault(
            reg, {"count_r_lt_1_00": 0, "count_r_over_atr_lt_0_5": 0, "total": 0}
        )
        micro_stops_by_regime[reg]["total"] += 1
        if r < Decimal("1.00"):
            micro_stops_by_regime[reg]["count_r_lt_1_00"] += 1
        if r_over_atr < Decimal("0.50"):
            micro_stops_by_regime[reg]["count_r_over_atr_lt_0_5"] += 1

        net_pnl = t.realized_pnl - t.fees_paid - t.funding_paid
        rec = {
            "trade_id": t.trade_id,
            "entry_time": t.entry_time,
            "exit_time": t.exit_time,
            "entry_price": float(t.entry_price),
            "exit_price": float(t.exit_price) if t.exit_price else None,
            "initial_stop": float(d.initial_stop),
            "initial_r": float(d.initial_r),
            "atr_at_entry": float(d.atr_at_entry),
            "r_over_atr": float(r_over_atr),
            "position_size": float(t.size),
            "notional": float(t.notional),
            "is_dca": t.is_dca,
            "exit_reason": t.exit_reason,
            "realized_pnl": float(t.realized_pnl),
            "fees_paid": float(t.fees_paid),
            "net_pnl": float(net_pnl),
            "mfe_price": float(d.mfe),
            "mfe_r": float(d.mfe_r),
            "mae_price": float(d.mae),
            "r_realized": float(d.realized_r),
            "r_surrendered": float(max(Decimal("0.0"), d.mfe_r - d.realized_r)),
            "regime": d.regime,
            "entry_family": d.entry_family,
        }
        all_trade_records.append(rec)

        if t.is_dca:
            dca_trades.append(rec)
        else:
            non_dca_trades.append(rec)

    # 2. Compare DCA vs Non-DCA Performance
    def compute_group_stats(group: list[dict[str, Any]]) -> dict[str, Any]:
        if not group:
            return {}
        n = len(group)
        wins = [x for x in group if x["net_pnl"] > 0]
        losses = [x for x in group if x["net_pnl"] < 0]
        gross_w = sum(x["realized_pnl"] for x in wins)
        gross_l = abs(sum(x["realized_pnl"] for x in losses))
        net_pnl = sum(x["net_pnl"] for x in group)
        fees = sum(x["fees_paid"] for x in group)
        pf = float(gross_w / gross_l) if gross_l > 0 else 0.0
        avg_r = sum(x["r_realized"] for x in group) / n
        r_list = sorted([x["r_realized"] for x in group])
        median_r = r_list[n // 2]
        return {
            "total_trades": n,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(len(wins) / n * 100, 2),
            "gross_profit": round(gross_w, 2),
            "gross_loss": round(gross_l, 2),
            "net_pnl": round(net_pnl, 2),
            "profit_factor": round(pf, 3),
            "total_fees": round(fees, 2),
            "avg_r_realized": round(avg_r, 3),
            "median_r_realized": round(median_r, 3),
            "avg_loss_dollars": (
                round(sum(x["net_pnl"] for x in losses) / len(losses), 2) if losses else 0
            ),
            "avg_win_dollars": (
                round(sum(x["net_pnl"] for x in wins) / len(wins), 2) if wins else 0
            ),
            "max_loss_dollars": round(min(x["net_pnl"] for x in group), 2),
            "avg_mfe_r": round(sum(x["mfe_r"] for x in group) / n, 2),
            "avg_r_surrendered": round(sum(x["r_surrendered"] for x in group) / n, 2),
        }

    dca_stats = compute_group_stats(dca_trades)
    non_dca_stats = compute_group_stats(non_dca_trades)

    # 3. Detailed Autopsy of Trade e409b654
    # Replay candle-by-candle for Trade e409b654
    target_trade = next((t for t in all_trade_records if t["trade_id"] == "e409b654"), None)

    audit_summary = {
        "dataset_candles": len(candles),
        "total_trades": len(all_trade_records),
        "micro_stop_audit": {
            "summary": micro_stops,
            "by_entry_family": micro_stops_by_family,
            "by_regime": micro_stops_by_regime,
        },
        "dca_vs_non_dca_comparison": {
            "dca_trades_stats": dca_stats,
            "non_dca_trades_stats": non_dca_stats,
        },
        "trade_e409b654_autopsy": target_trade,
    }

    import os

    os.makedirs("scratch", exist_ok=True)
    with open("scratch/phase_4a_audit_output.json", "w") as f:
        json.dump(audit_summary, f, indent=2)
    with open("phase_4a_integrity_audit.json", "w") as f:
        json.dump(audit_summary, f, indent=2)

    print("Phase 4A Audit Script Finished successfully. Output in phase_4a_integrity_audit.json")
    return audit_summary


if __name__ == "__main__":
    run_full_audit()
