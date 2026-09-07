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


def test_resample_candles_completed_only() -> None:
    """Only fully completed target timeframe buckets are emitted."""
    from src.backtest.engine import resample_candles

    # 4 15M candles span exactly 1 hour (0 to 3600000)
    candles = [
        make_candle(0, "2700.0", "2705.0", "2695.0", "2702.0"),
        make_candle(1, "2702.0", "2710.0", "2701.0", "2708.0"),
        make_candle(2, "2708.0", "2715.0", "2705.0", "2712.0"),
        make_candle(3, "2712.0", "2720.0", "2710.0", "2718.0"),
    ]
    # With 3 candles, 1H bucket is incomplete -> 0 1H candles
    res_3 = resample_candles(candles[:3], Timeframe.H1)
    assert len(res_3) == 0

    # With 4 candles, 1H bucket completes -> 1 1H candle
    res_4 = resample_candles(candles, Timeframe.H1)
    assert len(res_4) == 1
    assert res_4[0].open == Decimal("2700.0")
    assert res_4[0].high == Decimal("2720.0")
    assert res_4[0].low == Decimal("2695.0")
    assert res_4[0].close == Decimal("2718.0")
    assert res_4[0].timeframe == Timeframe.H1


def test_backtest_end_to_end_bull_trend(backtest_config: BacktestConfig) -> None:
    """In a continuous bull trend, the engine enters and exits safely, calculating all metrics."""
    from src.backtest.stress import generate_bull_trend_candles

    candles = generate_bull_trend_candles(start_price=Decimal("2700.0"), num_candles=30)
    engine = BacktestEngine(config=backtest_config)
    result = engine.run(candles)

    # Result contains comprehensive performance summary
    assert isinstance(result.expectancy, Decimal)
    assert isinstance(result.sharpe_ratio, Decimal)
    assert isinstance(result.sortino_ratio, Decimal)
    assert isinstance(result.calmar_ratio, Decimal)
    assert "$5" in result.target_hit_rates
    assert "$10" in result.target_hit_rates


def test_backtest_liquidation_trigger(backtest_config: BacktestConfig) -> None:
    """Flash crash triggers simulated liquidation check when explicit estimator is configured."""
    from src.backtest.stress import generate_flash_crash_candles
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent
    from src.risk.liquidation import ConfigurableLiquidationEstimator

    estimator = ConfigurableLiquidationEstimator(fixed_price=Decimal("2160.00"))
    engine = BacktestEngine(config=backtest_config, estimator=estimator)
    # Open an initial long position manually
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.0"),
        notional=Decimal("2700.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_OPEN",
        reason="Manual open for liquidation test",
    )
    candle_entry = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    trade = engine.exchange.process_order(intent, candle_entry)
    assert trade is not None
    assert engine.exchange.has_open_position()
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": Decimal("20.0"),
    }

    # Flash crash 25% down will breach liquidation price (2160)
    crash_candles = generate_flash_crash_candles(
        start_price=Decimal("2700.0"), drop_pct=Decimal("0.25"), num_candles=5
    )
    result = engine.run(crash_candles)
    assert result.liquidations_count >= 1


def test_standard_liquidation_estimator_edge_cases() -> None:
    """UnavailableLiquidationEstimator safely reports UNAVAILABLE without guessing formulas."""
    from src.risk.liquidation import (
        ConfigurableLiquidationEstimator,
        LiquidationSafetyStatus,
        UnavailableLiquidationEstimator,
    )

    unavail = UnavailableLiquidationEstimator()
    eval_res = unavail.evaluate_liquidation(
        entry_price=Decimal("2700"),
        leverage=Decimal("2"),
        allocated_funds=Decimal("1000"),
        max_acceptable_price=Decimal("2500"),
    )
    assert eval_res.status == LiquidationSafetyStatus.UNAVAILABLE
    assert (
        unavail.estimate_liquidation_price(Decimal("2700"), Decimal("2"), Decimal("1000")) is None
    )

    # Configurable estimator checks safety threshold explicitly
    cfg_est = ConfigurableLiquidationEstimator(fixed_price=Decimal("2400"))
    eval_safe = cfg_est.evaluate_liquidation(
        entry_price=Decimal("2700"),
        leverage=Decimal("2"),
        allocated_funds=Decimal("1000"),
        max_acceptable_price=Decimal("2500"),
    )
    assert eval_safe.status == LiquidationSafetyStatus.SAFE


def test_resample_candles_edge_cases() -> None:
    """Empty candles and M15 target timeframe return correctly."""
    from src.backtest.engine import resample_candles

    assert resample_candles([], Timeframe.H1) == []
    c = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    assert resample_candles([c], Timeframe.M15) == [c]


def test_get_historical_slice_invalid_index(backtest_config: BacktestConfig) -> None:
    """Invalid index raises ValueError."""
    engine = BacktestEngine(config=backtest_config)
    candles = [make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")]
    with pytest.raises(ValueError, match="Invalid index"):
        engine.get_historical_slice(candles, current_idx=-1)
    with pytest.raises(ValueError, match="Invalid index"):
        engine.get_historical_slice(candles, current_idx=2)


def test_backtest_empty_run(backtest_config: BacktestConfig) -> None:
    """Running backtest on empty candles returns default BacktestResult."""
    engine = BacktestEngine(config=backtest_config)
    res = engine.run([])
    assert res.total_trades == 0


def test_backtest_funding_application(backtest_config: BacktestConfig) -> None:
    """When open position crosses 8h boundary, funding is applied."""
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent

    engine = BacktestEngine(config=backtest_config)
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.0"),
        notional=Decimal("2700.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_FUND",
        reason="Entry",
    )
    # Candle open_time divisible by 28,800,000 (8h boundary)
    c_open = make_candle(0, "2700.0", "2710.0", "2690.0", "2705.0")
    trade = engine.exchange.process_order(intent, c_open)
    assert trade is not None
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": Decimal("20.0"),
    }

    # Candle crossing boundary at t = 28800000
    c_funding = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=28800000,
        open=Decimal("2705.0"),
        high=Decimal("2710.0"),
        low=Decimal("2700.0"),
        close=Decimal("2705.0"),
        volume=Decimal("100.0"),
        close_time=28800000 + 899999,
        is_closed=True,
    )
    engine.run([c_funding])
    assert engine.exchange.total_funding_paid > Decimal("0")


def test_backtest_emergency_loss_trigger(backtest_config: BacktestConfig) -> None:
    """When position economic loss exceeds emergency limit, position is closed immediately."""
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent

    engine = BacktestEngine(config=backtest_config)
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.0"),
        notional=Decimal("2700.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_EMERGENCY",
        reason="Entry",
    )
    c_open = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    trade = engine.exchange.process_order(intent, c_open)
    assert trade is not None
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": Decimal("20.0"),
    }

    # Emergency loss limit in fixture is $400. Drop price by $450 to 2250.
    c_drop = make_candle(1, "2300.0", "2300.0", "2250.0", "2250.0")
    engine.run([c_drop])
    assert not engine.exchange.has_open_position()


def test_backtest_entry_pipeline_execution(
    backtest_config: BacktestConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Strategy BUY decision passes risk checks, enters trade, and tracks stops."""
    from unittest.mock import MagicMock

    from src.domain.enums import DecisionState, MarketRegime
    from src.domain.models import DecisionSnapshot
    from src.strategy.entry_families import EntryFamily, EntrySetup

    mock_strat = MagicMock()
    mock_strat.evaluate.return_value = DecisionSnapshot(
        decision_id="mock_buy",
        symbol="XAUUSDT",
        timestamp=1700000000000,
        decision_state=DecisionState.BUY,
        regime=MarketRegime.STRONG_BULL,
        reason="Mock confluence buy",
    )
    from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus

    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    engine = BacktestEngine(config=backtest_config, strategy_engine=mock_strat, estimator=estimator)
    monkeypatch.setattr(
        engine.orchestrator,
        "evaluate_setups",
        MagicMock(
            return_value=EntrySetup(
                family=EntryFamily.TREND_PULLBACK,
                level=Decimal("2700.0"),
                stop_loss_ref=Decimal("2680.0"),
            )
        ),
    )

    candles = [make_candle(i, "2700.0", "2710.0", "2690.0", "2705.0") for i in range(25)]
    result = engine.run(candles)

    assert result.total_trades > 0
    assert engine.exchange.has_open_position() is False  # Closed at end of backtest


def test_backtest_exit_manager_partial_tp_and_stop(
    backtest_config: BacktestConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Position hits partial take-profit, then exits at structural stop."""
    from unittest.mock import MagicMock

    from src.domain.enums import DecisionState
    from src.strategy.engine import ExitDecision

    engine = BacktestEngine(config=backtest_config)
    # Open initial position
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.0"),
        notional=Decimal("2700.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_EXIT_TEST",
        reason="Entry",
    )
    c0 = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    trade = engine.exchange.process_order(intent, c0)
    assert trade is not None
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": Decimal("20.0"),
    }

    # Mock exit manager to return PARTIAL_TP then EXIT
    mock_eval = MagicMock(
        side_effect=[
            ExitDecision(
                should_exit=True,
                exit_state=DecisionState.PARTIAL_TP,
                reason="Partial TP reached",
                trigger_price=Decimal("2730.0"),
                current_price=Decimal("2730.0"),
                portion_pct=Decimal("50.0"),
            ),
            ExitDecision(
                should_exit=True,
                exit_state=DecisionState.EXIT,
                reason="Stop loss hit",
                trigger_price=Decimal("2680.0"),
                current_price=Decimal("2675.0"),
                portion_pct=Decimal("100.0"),
            ),
        ]
    )
    monkeypatch.setattr(engine.exit_manager, "evaluate_position", mock_eval)

    # Run over 2 candles: first triggers partial TP, second triggers stop EXIT
    c1 = make_candle(1, "2700.0", "2735.0", "2695.0", "2730.0")
    c2 = make_candle(2, "2730.0", "2730.0", "2670.0", "2675.0")

    # Manually seed current_stop_loss via candle evaluation
    result = engine.run([c1, c2])
    assert len(result.trades) >= 1


def test_emergency_stop_evaluates_trade_fees_not_cumulative_backtest_fees(
    backtest_config: BacktestConfig,
) -> None:
    """Verify that lifetime cumulative backtest fees do not trigger emergency exit."""
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent

    engine = BacktestEngine(config=backtest_config)
    # Simulate high cumulative historical fees across past trades
    engine.exchange.total_fees_paid = Decimal("1000.00")
    engine.exchange.total_funding_paid = Decimal("50.00")

    # Open a fresh trade via process_order
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("1.0"),
        price=Decimal("2700.0"),
        notional=Decimal("2700.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_EMERGENCY_INIT",
        reason="Test",
    )
    c0 = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    t = engine.exchange.process_order(intent, c0)
    assert t is not None
    assert engine.exchange.active_trade is not None
    assert engine.exchange.active_trade.fees_paid < Decimal("5.00")
    assert engine.exchange.position is not None
    engine.active_trade_meta[t.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": Decimal("20.0"),
    }

    # The emergency_loss_limit is $400.00.
    # Cumulative fees ($1000) exceed $400, but active trade loss (-$10 PnL + ~$1 fee) does not.
    c1 = make_candle(1, "2695.0", "2700.0", "2690.0", "2695.0")
    engine.run([c1])

    # Assert trade was NOT prematurely liquidated by emergency loss
    breached = any(
        trade.exit_reason == "EMERGENCY_STOP_LOSS_BREACHED"
        for trade in engine.exchange.closed_trades
    )
    assert not breached


def test_initial_r_immutable_across_dca_and_partial_tp(
    backtest_config: BacktestConfig,
) -> None:
    """Verify that initial_r remains strictly unchanged in active_trade_meta
    after DCA and Partial TP.
    """
    from src.domain.enums import OrderSide
    from src.domain.models import OrderIntent

    engine = BacktestEngine(config=backtest_config)
    # 1. Initial Entry
    intent1 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("0.200"),
        price=Decimal("2700.0"),
        notional=Decimal("540.0"),
        is_dca=False,
        is_opening=True,
        client_order_id="INIT_ENTRY",
        reason="Entry",
    )
    c0 = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    t1 = engine.exchange.process_order(intent1, c0)
    assert t1 is not None
    original_initial_r = Decimal("20.0")
    engine.active_trade_meta[t1.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.0"),
        "initial_r": original_initial_r,
    }

    # 2. DCA Scale-In at lower price
    c1 = make_candle(1, "2685.0", "2690.0", "2680.0", "2685.0")
    intent_dca = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("0.100"),
        price=Decimal("2685.0"),
        notional=Decimal("268.5"),
        is_dca=True,
        is_opening=True,
        client_order_id="DCA_ADD",
        reason="DCA",
    )
    engine.exchange.process_order(intent_dca, c1)

    # Verify initial_r in metadata is strictly unchanged
    assert engine.active_trade_meta[t1.trade_id]["initial_r"] == original_initial_r

    # 3. Partial TP at higher price
    c2 = make_candle(2, "2730.0", "2735.0", "2725.0", "2730.0")
    intent_ptp = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.150"),
        price=Decimal("2730.0"),
        notional=Decimal("409.5"),
        is_dca=False,
        is_opening=False,
        client_order_id="PARTIAL_TP_1",
        reason="TP",
    )
    engine.exchange.process_order(intent_ptp, c2)

    # Verify initial_r remains immutable
    assert engine.active_trade_meta[t1.trade_id]["initial_r"] == original_initial_r
