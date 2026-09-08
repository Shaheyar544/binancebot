"""Phase 5: Strategy Profitability Remediation Full Canonical Backtest Runner.

Executes the full 25,857-candle backtest under Phase 5 rules:
- TP1 at 1.5R (50%) + TP2 at 3.0R (remaining runner)
- TrendPullback requiring EMA20 > EMA50 (no bearish crosses)
- Multi-candle BreakoutRetest with proof of breakout from below
- Composite Regime Invalidation exit (BEAR, STRONG_BEAR, BEARISH_RANGE)
- Stale initial_r recalculated after DCA
- Max holding time exit (48 hours)
- High-Conviction DCA Qualification (>=85, 1D/4H/1H bullish, drawdown >= -0.5R)
- Monotonic +1.0R Breakeven with dynamic ATR buffer
"""

import json
import os
from decimal import Decimal
from typing import Any

from scripts.diagnose_phase_3a import load_candles
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.config.settings import UserRiskConfig
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager, StrategyEngine


def run_phase_5_backtest() -> dict[str, Any]:
    candles = load_candles()

    risk_config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
        max_entries=3,
        risk_per_trade_pct=Decimal("1.0"),
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("2000.00"),
        max_holding_time_hours=48,
    )
    cfg = BacktestConfig(user_risk_config=risk_config)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2000.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    strat_engine = StrategyEngine(min_entry_score=85)
    exit_mgr = ExitManager(
        partial_tp_ratio=Decimal("1.5"),
        partial_tp_pct=Decimal("50.0"),
        final_tp_ratio=Decimal("3.0"),
        trailing_atr_multiplier=Decimal("2.0"),
        enable_breakeven=True,
        breakeven_r_multiple=Decimal("1.0"),
        max_holding_hours=48,
    )

    engine = BacktestEngine(
        config=cfg,
        strategy_engine=strat_engine,
        exit_manager=exit_mgr,
        estimator=estimator,
    )

    res = engine.run(candles)
    trades = res.trades

    dca_trades = [t for t in trades if t.is_dca]
    non_dca_trades = [t for t in trades if not t.is_dca]

    def compute_stats(group: list[Any]) -> dict[str, Any]:
        if not group:
            return {"trades": 0}
        w = [t for t in group if t.realized_pnl > Decimal("0")]
        losses_list = [t for t in group if t.realized_pnl < Decimal("0")]
        gp = sum((t.realized_pnl for t in w), Decimal("0"))
        gl = abs(sum((t.realized_pnl for t in losses_list), Decimal("0")))
        net = gp - gl
        pf = (
            gp / gl
            if gl > Decimal("0")
            else (Decimal("100.0") if gp > Decimal("0") else Decimal("0"))
        )
        fees = sum((t.fees_paid for t in group), Decimal("0"))
        funding = sum((t.funding_paid for t in group), Decimal("0"))
        return {
            "trades": len(group),
            "wins": len(w),
            "losses": len(losses_list),
            "win_rate": float(
                round(Decimal(str(len(w))) / Decimal(str(len(group))) * Decimal("100.0"), 2)
            ),
            "gross_profit": float(round(gp, 2)),
            "gross_loss": float(round(gl, 2)),
            "net_pnl": float(round(net, 2)),
            "profit_factor": float(round(pf, 3)),
            "fees_paid": float(round(fees, 2)),
            "funding_paid": float(round(funding, 2)),
            "net_after_fees": float(round(net - fees - funding, 2)),
        }

    results: dict[str, Any] = {
        "dataset_candles": len(candles),
        "overall": {
            "total_trades": res.total_trades,
            "winning_trades": res.winning_trades,
            "losing_trades": res.losing_trades,
            "win_rate": float(round(res.win_rate * Decimal("100.0"), 2)),
            "net_profit": float(round(res.net_profit, 2)),
            "profit_factor": float(round(res.profit_factor, 3)),
            "max_drawdown_pct": float(round(res.max_drawdown_pct * Decimal("100.0"), 2)),
            "total_fees_paid": float(round(res.total_fees, 2)),
            "maker_fees_paid": float(round(res.total_maker_fees, 2)),
            "taker_fees_paid": float(round(res.total_taker_fees, 2)),
            "funding_paid": float(round(res.total_funding, 2)),
            "expectancy": float(res.expectancy),
            "sharpe_ratio": float(res.sharpe_ratio),
            "sortino_ratio": float(res.sortino_ratio),
        },
        "dca_trades": compute_stats(dca_trades),
        "non_dca_trades": compute_stats(non_dca_trades),
        "setup_family_performance": {
            k: {
                "trades": int(v["total_trades"]),
                "win_rate": float(round(v["win_rate"] * Decimal("100.0"), 2)),
                "net_pnl": float(round(v["net_pnl"], 2)),
                "profit_factor": float(round(v["profit_factor"], 3)),
            }
            for k, v in res.setup_family_performance.items()
        },
        "regime_performance": {
            k: {
                "trades": int(v["total_trades"]),
                "win_rate": float(round(v["win_rate"] * Decimal("100.0"), 2)),
                "net_pnl": float(round(v["net_pnl"], 2)),
                "profit_factor": float(round(v["profit_factor"], 3)),
            }
            for k, v in res.regime_performance.items()
        },
    }

    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "phase_5_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("\n=======================================================")
    print("        PHASE 5 CANONICAL BACKTEST RESULTS             ")
    print("=======================================================")
    print(f"Total Trades:       {results['overall']['total_trades']}")
    print(f"Win Rate:           {results['overall']['win_rate']:.2f}%")
    print(f"Net P&L:            ${results['overall']['net_profit']:.2f}")
    print(f"Profit Factor:      {results['overall']['profit_factor']:.3f}")
    print(f"Max Drawdown:       {results['overall']['max_drawdown_pct']:.2f}%")
    print(f"Total Fees Paid:    ${results['overall']['total_fees_paid']:.2f}")
    print(f"  - Taker Fees:     ${results['overall']['taker_fees_paid']:.2f}")
    print(f"  - Maker Fees:     ${results['overall']['maker_fees_paid']:.2f}")
    print("-------------------------------------------------------")
    dca_pnl = results["dca_trades"].get("net_pnl", 0.0)
    dca_wr = results["dca_trades"].get("win_rate", 0.0)
    non_dca_pnl = results["non_dca_trades"].get("net_pnl", 0.0)
    non_dca_wr = results["non_dca_trades"].get("win_rate", 0.0)
    print(f"DCA Trades Net P&L: ${dca_pnl:.2f} (WR: {dca_wr:.2f}%)")
    print(f"Non-DCA Net P&L:    ${non_dca_pnl:.2f} (WR: {non_dca_wr:.2f}%)")
    print("=======================================================\n")

    return results


if __name__ == "__main__":
    run_phase_5_backtest()
