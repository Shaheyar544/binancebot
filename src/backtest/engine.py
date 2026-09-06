"""Event-driven no-lookahead backtesting engine."""

from collections.abc import Sequence
from decimal import Decimal

from src.backtest.exchange import SimulatedExchange
from src.backtest.models import BacktestConfig, BacktestResult, SimulatedTrade
from src.domain.models import Candle


class BacktestEngine:
    """Orchestrates chronological forward simulation across historical candles."""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.exchange = SimulatedExchange(config=config)

    def get_historical_slice(
        self,
        candles: Sequence[Candle],
        current_idx: int,
    ) -> list[Candle]:
        """Return finalized candles strictly up to current_idx with zero future data."""
        if current_idx < 0 or current_idx >= len(candles):
            raise ValueError(f"Invalid index {current_idx} for sequence of length {len(candles)}")
        return list(candles[: current_idx + 1])

    def is_news_locked(self, timestamp: int) -> bool:
        """Check if timestamp is within [event - 24h, event + 24h] for any event."""
        lock_window_ms = 24 * 3600 * 1000  # 24 hours in milliseconds
        for event_time in self.config.news_event_timestamps:
            if (event_time - lock_window_ms) <= timestamp <= (event_time + lock_window_ms):
                return True
        return False

    def run(self, candles: Sequence[Candle]) -> BacktestResult:
        """Run event-driven simulation over chronological candles."""
        trades: list[SimulatedTrade] = list(self.exchange.closed_trades)

        total_trades = len(trades)
        wins = [t for t in trades if t.realized_pnl > Decimal("0.0")]
        losses = [t for t in trades if t.realized_pnl < Decimal("0.0")]

        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (
            Decimal(str(winning_trades)) / Decimal(str(total_trades))
            if total_trades > 0
            else Decimal("0.0")
        )

        gross_profit = sum((t.realized_pnl for t in wins), Decimal("0.0"))
        gross_loss = abs(sum((t.realized_pnl for t in losses), Decimal("0.0")))
        net_profit = gross_profit - gross_loss
        profit_factor = gross_profit / gross_loss if gross_loss > Decimal("0.0") else Decimal("0.0")

        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            net_profit=net_profit,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=profit_factor,
            total_fees=self.exchange.total_fees_paid,
            total_funding=self.exchange.total_funding_paid,
            liquidations_count=self.exchange.liquidations_count,
            trades=trades,
        )
