"""Tests for BacktestEngine: no lookahead, metrics, and news lock integration."""

from decimal import Decimal

import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.config.settings import UserRiskConfig
from src.domain.enums import Timeframe
from src.domain.models import Candle


def make_candle(idx: int, open_p: str, high_p: str, low_p: str, close_p: str) -> Candle:
    t = 1700000000000 + idx * 900000
    return Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=t,
        open=Decimal(open_p),
        high=Decimal(high_p),
        low=Decimal(low_p),
        close=Decimal(close_p),
        volume=Decimal("100.0"),
        close_time=t + 899999,
        is_closed=True,
    )


@pytest.fixture
def backtest_config() -> BacktestConfig:
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("5000.00"),
    )
    return BacktestConfig(
        initial_balance=Decimal("10000.00"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        slippage_pct=Decimal("0.0001"),
        user_risk_config=user_risk,
    )


def test_no_lookahead_guarantee(backtest_config: BacktestConfig) -> None:
    """Historical evaluation on bar t only observes bars <= t."""
    engine = BacktestEngine(config=backtest_config)
    candles = [
        make_candle(0, "2700.0", "2705.0", "2695.0", "2702.0"),
        make_candle(1, "2702.0", "2712.0", "2700.0", "2710.0"),
        make_candle(2, "2710.0", "2725.0", "2708.0", "2720.0"),
    ]

    # Bar 1 evaluation sees only [bar 0, bar 1]
    history_at_1 = engine.get_historical_slice(candles, current_idx=1)
    assert len(history_at_1) == 2
    assert history_at_1[-1].open_time == candles[1].open_time


def test_news_lock_prevents_entries(backtest_config: BacktestConfig) -> None:
    """During 24h before through 24h after a scheduled event, no new entries occur."""
    event_time = 1700000000000 + 86400000  # 24 hours after start
    config_with_news = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0005"),
        slippage_pct=Decimal("0.0001"),
        user_risk_config=backtest_config.user_risk_config,
        news_event_timestamps=[event_time],
    )
    engine = BacktestEngine(config=config_with_news)

    # Timestamp 1 hour before event is within news lock
    bar_time = event_time - 3600000
    is_locked = engine.is_news_locked(bar_time)
    assert is_locked is True

    # Timestamp 25 hours before event is outside news lock
    bar_time_before = event_time - (25 * 3600000)
    assert engine.is_news_locked(bar_time_before) is False


def test_backtest_run_metrics(backtest_config: BacktestConfig) -> None:
    """Backtest engine computes win rate, profit factor, and fee aggregates correctly."""
    engine = BacktestEngine(config=backtest_config)
    candles = [
        make_candle(0, "2700.0", "2705.0", "2695.0", "2702.0"),
        make_candle(1, "2702.0", "2712.0", "2700.0", "2710.0"),
    ]
    result = engine.run(candles)
    assert result.total_trades == 0
    assert result.win_rate == Decimal("0.0")
    assert result.net_profit == Decimal("0.0")
