"""Phase 3A: Baseline Strategy Diagnostics Runner and Analyzer.

Evaluates the clean pre-optimization baseline (commit e382515) without changing
any strategy parameters, entry thresholds, risk rules, or exit logic.
"""

import json
from decimal import Decimal
from typing import Any

from src.backtest.engine import BacktestEngine
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    LiquidationModelPolicy,
    PerTradeDiagnostic,
)
from src.config.settings import UserRiskConfig
from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus


def load_candles(filepath: str = "data/xauusdt_15m.json") -> list[Candle]:
    """Load historical 15m candles."""
    with open(filepath, encoding="utf-8") as f:
        raw_list = json.load(f)

    candles = [
        Candle(
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
        for item in raw_list
    ]
    candles.sort(key=lambda c: c.open_time)
    return candles


def run_diagnostics() -> dict[str, Any]:
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
        reason="Phase 3A baseline evaluation tier",
    )

    engine = BacktestEngine(config=config, estimator=estimator)
    result = engine.run(candles)
    diags: list[PerTradeDiagnostic] = result.diagnostics

    # 1. Overall R metrics
    r_list = [d.realized_r for d in diags]
    sorted_r = sorted(r_list)
    median_r = sorted_r[len(sorted_r) // 2] if sorted_r else Decimal("0.0")
    avg_r = sum(r_list, Decimal("0.0")) / Decimal(str(len(r_list))) if r_list else Decimal("0.0")

    # 2. Positive MFE closing as loser
    pos_mfe_losers = [d for d in diags if d.net_pnl < Decimal("0.0") and d.mfe > Decimal("0.0")]
    pos_mfe_loser_pct = (
        Decimal(str(len(pos_mfe_losers))) / Decimal(str(len(diags))) * Decimal("100.0")
        if diags
        else Decimal("0.0")
    )

    # 3. Trades reaching >= 1.0R but failing to realize >= 1.0R (or closing as losers)
    r1_reached = [d for d in diags if d.max_r_reached >= Decimal("1.0")]
    r1_reached_not_realized = [d for d in r1_reached if d.realized_r < Decimal("1.0")]
    r1_reached_closed_loser = [d for d in r1_reached if d.net_pnl < Decimal("0.0")]

    # 4. DCA vs No-DCA Breakdown
    dca_trades = [d for d in diags if d.dca_count > 0]
    nodca_trades = [d for d in diags if d.dca_count == 0]

    def _calc_subset_stats(subset: list[PerTradeDiagnostic]) -> dict[str, Any]:
        count = len(subset)
        if count == 0:
            return {"count": 0}
        wins = [d for d in subset if d.net_pnl > Decimal("0.0")]
        losses = [d for d in subset if d.net_pnl < Decimal("0.0")]
        gross_win = sum((d.gross_pnl for d in wins), Decimal("0.0"))
        gross_loss = abs(sum((d.gross_pnl for d in losses), Decimal("0.0")))
        net = sum((d.net_pnl for d in subset), Decimal("0.0"))
        fees = sum((d.fees_paid for d in subset), Decimal("0.0"))
        pf = round(gross_win / gross_loss, 2) if gross_loss > Decimal("0.0") else Decimal("0.0")
        wr = round(Decimal(str(len(wins))) / Decimal(str(count)), 4)
        avg_r_sub = sum((d.realized_r for d in subset), Decimal("0.0")) / Decimal(str(count))
        mfe_r_sub = sum((d.mfe_r for d in subset), Decimal("0.0")) / Decimal(str(count))
        mae_sub = sum((d.mae for d in subset), Decimal("0.0")) / Decimal(str(count))
        mfe_sub = sum((d.mfe for d in subset), Decimal("0.0")) / Decimal(str(count))
        return {
            "count": count,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": str(round(wr * Decimal("100.0"), 2)) + "%",
            "gross_profit": str(round(gross_win, 2)),
            "gross_loss": str(round(gross_loss, 2)),
            "net_profit": str(round(net, 2)),
            "profit_factor": str(pf),
            "fees": str(round(fees, 2)),
            "avg_r": str(round(avg_r_sub, 2)),
            "avg_mfe_r": str(round(mfe_r_sub, 2)),
            "avg_mfe": str(round(mfe_sub, 2)),
            "avg_mae": str(round(mae_sub, 2)),
        }

    dca_stats = _calc_subset_stats(dca_trades)
    nodca_stats = _calc_subset_stats(nodca_trades)

    # 5. Largest giveback patterns
    giveback_diags = [d for d in diags if (d.max_r_reached - d.realized_r) > Decimal("0.0")]
    giveback_diags.sort(key=lambda d: d.max_r_reached - d.realized_r, reverse=True)
    top_givebacks = [
        {
            "trade_id": d.trade_id,
            "family": d.entry_family,
            "regime": d.regime,
            "entry_score": str(d.entry_score),
            "max_r": str(d.max_r_reached),
            "realized_r": str(d.realized_r),
            "r_surrendered": str(round(d.max_r_reached - d.realized_r, 2)),
            "mfe": str(d.mfe),
            "exit_reason": d.exit_reason,
            "net_pnl": str(round(d.net_pnl, 2)),
        }
        for d in giveback_diags[:10]
    ]

    # 6. Exit Reason Distribution
    exit_reasons: dict[str, int] = {}
    for d in diags:
        exit_reasons[d.exit_reason] = exit_reasons.get(d.exit_reason, 0) + 1

    r_targets = result.r_target_hit_rates
    report_data = {
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
            "pos_mfe_losers_pct_of_all": str(round(pos_mfe_loser_pct, 2)) + "%",
        },
        "r_target_reach": {
            "0.5R": str(round(r_targets.get("0.5R", Decimal("0.0")) * 100, 1)) + "%",
            "1.0R": str(round(r_targets.get("1.0R", Decimal("0.0")) * 100, 1)) + "%",
            "1.5R": str(round(r_targets.get("1.5R", Decimal("0.0")) * 100, 1)) + "%",
            "2.0R": str(round(r_targets.get("2.0R", Decimal("0.0")) * 100, 1)) + "%",
            "r1_reached_count": len(r1_reached),
            "r1_not_realized_count": len(r1_reached_not_realized),
            "r1_not_realized_pct": (
                str(
                    round(
                        Decimal(str(len(r1_reached_not_realized)))
                        / Decimal(str(len(r1_reached)))
                        * Decimal("100.0"),
                        2,
                    )
                )
                + "%"
                if r1_reached
                else "0.0%"
            ),
            "r1_closed_as_loser_count": len(r1_reached_closed_loser),
            "r1_closed_as_loser_pct": (
                str(
                    round(
                        Decimal(str(len(r1_reached_closed_loser)))
                        / Decimal(str(len(r1_reached)))
                        * Decimal("100.0"),
                        2,
                    )
                )
                + "%"
                if r1_reached
                else "0.0%"
            ),
        },
        "segments": {
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
            "dca_vs_nodca": {
                "no_dca": nodca_stats,
                "dca": dca_stats,
            },
        },
        "exit_reasons": exit_reasons,
        "top_givebacks": top_givebacks,
    }

    return report_data


if __name__ == "__main__":
    data = run_diagnostics()
    print(json.dumps(data, indent=2))
    with open("data/phase_3a_diagnostic_results.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
