"""Tests for Walk-Forward validation engine: zero-lookahead, fold generation, and stability."""

from decimal import Decimal

import pytest

from src.backtest.models import BacktestConfig
from src.backtest.stress import generate_bull_trend_candles
from src.backtest.walk_forward import WalkForwardEngine
from src.config.settings import UserRiskConfig


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


def test_walk_forward_invalid_params(backtest_config: BacktestConfig) -> None:
    """Zero or negative parameters must be rejected."""
    with pytest.raises(ValueError, match="strictly positive"):
        WalkForwardEngine(config=backtest_config, train_candles_count=0)


def test_walk_forward_zero_lookahead_guarantee(backtest_config: BacktestConfig) -> None:
    """Train window must strictly precede test window with zero temporal overlap."""
    candles = generate_bull_trend_candles(start_price=Decimal("2700.0"), num_candles=80)
    engine = WalkForwardEngine(
        config=backtest_config,
        train_candles_count=30,
        test_candles_count=10,
        step_candles_count=10,
    )

    folds = engine.generate_folds(candles)
    assert len(folds) >= 4

    for fold_idx, (train, test) in enumerate(folds):
        assert len(train) == 30
        assert len(test) == 10
        # Strict zero-lookahead invariant
        assert train[-1].close_time < test[0].open_time, (
            f"Fold {fold_idx} lookahead violation: train close {train[-1].close_time} >= "
            f"test open {test[0].open_time}"
        )


def test_walk_forward_anchored_folds(backtest_config: BacktestConfig) -> None:
    """Anchored folds always start at index 0 and expand."""
    candles = generate_bull_trend_candles(start_price=Decimal("2700.0"), num_candles=80)
    engine = WalkForwardEngine(
        config=backtest_config,
        train_candles_count=30,
        test_candles_count=10,
        step_candles_count=10,
        anchored=True,
    )

    folds = engine.generate_folds(candles)
    assert len(folds) >= 4

    first_open_time = candles[0].open_time
    for train, test in folds:
        assert train[0].open_time == first_open_time
        assert train[-1].close_time < test[0].open_time


def test_walk_forward_execution(backtest_config: BacktestConfig) -> None:
    """Execute complete walk-forward evaluation across folds."""
    candles = generate_bull_trend_candles(start_price=Decimal("2700.0"), num_candles=60)
    engine = WalkForwardEngine(
        config=backtest_config,
        train_candles_count=25,
        test_candles_count=10,
        step_candles_count=10,
    )

    result = engine.run(candles)
    assert result.total_folds > 0
    assert len(result.folds) == result.total_folds
    assert result.stability_score >= Decimal("0.0")


def test_walk_forward_insufficient_data(backtest_config: BacktestConfig) -> None:
    """Fewer candles than train + test count yields 0 folds."""
    candles = generate_bull_trend_candles(start_price=Decimal("2700.0"), num_candles=20)
    engine = WalkForwardEngine(
        config=backtest_config,
        train_candles_count=30,
        test_candles_count=10,
    )
    result = engine.run(candles)
    assert result.total_folds == 0
    assert len(result.folds) == 0
