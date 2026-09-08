"""Phase 4C: High-Conviction DCA Qualification Remediation Backtest Runner.

Executes the full 25,857-candle backtest under Phase 4C rules:
- Score threshold >= 85 for DCA
- 1D, 4H, 1H bullish alignment
- 15M setup required
- $500 DCA notional cap
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


def run_phase_4c_backtest() -> dict[str, Any]:
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
    )
    cfg = BacktestConfig(user_risk_config=risk_config)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2000.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    strat_engine = StrategyEngine(min_entry_score=85)
    exit_mgr = ExitManager(enable_breakeven=True, breakeven_r_multiple=Decimal("1.0"))

    engine = BacktestEngine(
        config=cfg,
        strategy_engine=strat_engine,
        exit_manager=exit_mgr,
        estimator=estimator,
    )

    res = engine.run(candles)
    diag_map = {d.trade_id: d for d in res.diagnostics}
    trades = res.trades

    dca_trades = [t for t in trades if t.is_dca]
    non_dca_trades = [t for t in trades if not t.is_dca]

    def compute_stats(group: list[Any]) -> dict[str, Any]:
        if not group:
            return {"count": 0}
        n = len(group)
        wins = [x for x in group if x.realized_pnl - x.fees_paid - x.funding_paid > 0]
        losses = [x for x in group if x.realized_pnl - x.fees_paid - x.funding_paid < 0]
        gw = sum(x.realized_pnl for x in wins)
        gl = abs(sum(x.realized_pnl for x in losses))
        net = sum(x.realized_pnl - x.fees_paid - x.funding_paid for x in group)
        fees = sum(x.fees_paid for x in group)
        pf = float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)

        realized_rs = [
            float(diag_map[x.trade_id].realized_r) for x in group if x.trade_id in diag_map
        ]
        avg_r = sum(realized_rs) / len(realized_rs) if realized_rs else 0.0

        return {
            "total_trades": n,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": round(len(wins) / n * 100, 2),
            "gross_profit": round(float(gw), 2),
            "gross_loss": round(float(gl), 2),
            "net_pnl": round(float(net), 2),
            "profit_factor": round(pf, 3),
            "total_fees": round(float(fees), 2),
            "avg_r_realized": round(avg_r, 3),
            "avg_win_dollars": (
                round(
                    float(
                        sum(x.realized_pnl - x.fees_paid - x.funding_paid for x in wins) / len(wins)
                    ),
                    2,
                )
                if wins
                else 0.0
            ),
            "avg_loss_dollars": (
                round(
                    float(
                        sum(x.realized_pnl - x.fees_paid - x.funding_paid for x in losses)
                        / len(losses)
                    ),
                    2,
                )
                if losses
                else 0.0
            ),
            "max_loss_dollars": round(
                float(min(x.realized_pnl - x.fees_paid - x.funding_paid for x in group)), 2
            ),
        }

    overall_stats = {
        "dataset_candles": len(candles),
        "total_trades": len(trades),
        "winning_trades": int(res.winning_trades),
        "losing_trades": int(res.losing_trades),
        "win_rate_pct": round(float(res.win_rate) * 100, 2),
        "gross_profit": round(float(res.gross_profit), 2),
        "gross_loss": round(float(res.gross_loss), 2),
        "net_pnl": round(float(res.net_profit), 2),
        "profit_factor": round(float(res.profit_factor), 3),
        "total_fees": round(float(res.total_fees), 2),
        "maker_fees": round(float(res.total_maker_fees), 2),
        "taker_fees": round(float(res.total_taker_fees), 2),
        "max_drawdown_pct": round(float(res.max_drawdown_pct) * 100, 2),
        "dca_trades_count": len(dca_trades),
        "non_dca_trades_count": len(non_dca_trades),
        "dca_cohort_stats": compute_stats(dca_trades),
        "non_dca_cohort_stats": compute_stats(non_dca_trades),
    }

    os.makedirs("scratch", exist_ok=True)
    with open("scratch/phase_4c_backtest_output.json", "w") as f:
        json.dump(overall_stats, f, indent=2)
    with open("phase_4c_results.json", "w") as f:
        json.dump(overall_stats, f, indent=2)

    print("Phase 4C Backtest completed successfully.")
    print(
        f"Net PnL: ${overall_stats['net_pnl']} | PF: {overall_stats['profit_factor']} | "
        f"WinRate: {overall_stats['win_rate_pct']}% | DCA Trades: {len(dca_trades)}"
    )
    return overall_stats


if __name__ == "__main__":
    run_phase_4c_backtest()
