"""Tests for Phase 5 strategy profitability and risk remediation features."""

from decimal import Decimal

from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig
from src.config.settings import UserRiskConfig
from src.domain.enums import DecisionState, OrderSide, Timeframe
from src.domain.models import Candle, OrderIntent
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager
from src.strategy.entry_families import BreakoutRetestDetector, TrendPullbackDetector


def make_candle(
    idx: int,
    open_: str,
    high: str,
    low: str,
    close: str,
    vol: str = "100.0",
) -> Candle:
    base_t = 1700000000000 + idx * 900000
    return Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=base_t,
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(vol),
        close_time=base_t + 899999,
        is_closed=True,
    )


def test_trend_pullback_rejects_bearish_ema_cross() -> None:
    """TrendPullbackDetector must reject setups when EMA20 <= EMA50 (bearish cross)."""
    detector = TrendPullbackDetector()
    candle = make_candle(0, "2710.0", "2715.0", "2702.0", "2708.0")
    # ema_20 (2700) <= ema_50 (2705) -> bearish cross
    setup = detector.evaluate(
        candle=candle,
        ema_20=Decimal("2700.0"),
        ema_50=Decimal("2705.0"),
        atr=Decimal("5.0"),
    )
    assert setup is None

    # ema_20 (2705) > ema_50 (2700) -> valid uptrend
    valid_setup = detector.evaluate(
        candle=candle,
        ema_20=Decimal("2705.0"),
        ema_50=Decimal("2700.0"),
        atr=Decimal("5.0"),
    )
    assert valid_setup is not None


def test_breakout_retest_multicandle_scan() -> None:
    """BreakoutRetestDetector scans up to 5 candles back for confirmed breakout from below."""
    detector = BreakoutRetestDetector()
    resistance = Decimal("2720.0")
    atr = Decimal("4.0")

    # c0: below resistance (2715)
    # c1: breakout candle (closes 2725 > 2720)
    # c2: consolidation above resistance (2724)
    # c3: retest candle (low 2719 <= 2720, close 2723 > 2720)
    candles = [
        make_candle(0, "2710.0", "2718.0", "2708.0", "2715.0"),
        make_candle(1, "2716.0", "2726.0", "2714.0", "2725.0"),
        make_candle(2, "2724.0", "2728.0", "2722.0", "2724.0"),
        make_candle(3, "2724.0", "2726.0", "2719.0", "2723.0"),
    ]
    setup = detector.evaluate(candles, resistance_level=resistance, atr=atr)
    assert setup is not None
    assert setup.level == resistance


def test_breakout_retest_rejects_hovering_candles() -> None:
    """BreakoutRetestDetector rejects retest if prior candle was not below resistance."""
    detector = BreakoutRetestDetector()
    resistance = Decimal("2720.0")
    atr = Decimal("4.0")

    # If all prior candles were already hovering above resistance, it's not a fresh breakout
    candles = [
        make_candle(0, "2722.0", "2726.0", "2721.0", "2724.0"),  # closes above 2720
        make_candle(1, "2724.0", "2727.0", "2722.0", "2725.0"),  # closes above 2720
        make_candle(2, "2725.0", "2726.0", "2719.0", "2723.0"),  # dip and close above
    ]
    setup = detector.evaluate(candles, resistance_level=resistance, atr=atr)
    assert setup is None


def test_exit_manager_tp2_final_runner_target() -> None:
    """ExitManager triggers EXIT at final_tp_ratio (3.0R) when partial_tp_already_taken=True."""
    mgr = ExitManager(
        partial_tp_ratio=Decimal("1.5"),
        final_tp_ratio=Decimal("3.0"),
        trailing_atr_multiplier=Decimal("2.0"),
    )
    entry_p = Decimal("2700.00")
    stop_p = Decimal("2680.00")  # R = 20.00
    atr = Decimal("5.00")

    # TP1 is at 2730.00 (1.5R). At 2735.00, if partial TP not taken, gives PARTIAL_TP
    dec1 = mgr.evaluate_position(
        current_price=Decimal("2735.00"),
        entry_price=entry_p,
        stop_loss_ref=stop_p,
        atr=atr,
        highest_price_since_entry=Decimal("2735.00"),
        entry_timestamp=1000,
        current_timestamp=2000,
        partial_tp_already_taken=False,
    )
    assert dec1.exit_state == DecisionState.PARTIAL_TP
    assert dec1.portion_pct == Decimal("50.0")

    # Once partial TP taken, price reaches 2760.00 (3.0R) -> triggers EXIT for remaining 100%
    dec2 = mgr.evaluate_position(
        current_price=Decimal("2760.00"),
        entry_price=entry_p,
        stop_loss_ref=stop_p,
        atr=atr,
        highest_price_since_entry=Decimal("2760.00"),
        entry_timestamp=1000,
        current_timestamp=3000,
        partial_tp_already_taken=True,
    )
    assert dec2.exit_state == DecisionState.EXIT
    assert dec2.portion_pct == Decimal("100.0")
    assert "Final TP" in dec2.reason


def test_exit_manager_respects_enable_partial_tp_false() -> None:
    """ExitManager does not trigger partial TP when enable_partial_tp=False."""
    mgr = ExitManager(enable_partial_tp=False)
    dec = mgr.evaluate_position(
        current_price=Decimal("2750.00"),
        entry_price=Decimal("2700.00"),
        stop_loss_ref=Decimal("2680.00"),
        atr=Decimal("5.00"),
        highest_price_since_entry=Decimal("2750.00"),
        entry_timestamp=1000,
        current_timestamp=2000,
        partial_tp_already_taken=False,
    )
    assert dec.exit_state != DecisionState.PARTIAL_TP


def test_backtest_regime_invalidation_exit() -> None:
    """Backtest engine exits open position if composite regime turns hostile."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    cfg = BacktestConfig(user_risk_config=user_risk)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    engine = BacktestEngine(config=cfg, estimator=estimator)

    c_open = make_candle(0, "2700.0", "2710.0", "2695.0", "2705.0")
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("2705.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1082.00"),
        client_order_id="ENTRY_TEST",
        reason="Test",
    )
    trade = engine.exchange.process_order(intent, c_open)
    assert trade is not None
    assert engine.exchange.has_open_position()
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "STRONG_BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.00"),
        "initial_r": Decimal("25.00"),
        "configured_risk": Decimal("10.00"),
        "theoretical_risk": Decimal("10.00"),
        "actual_risk": Decimal("10.00"),
        "actual_risk_pct": Decimal("1.0"),
        "atr_at_entry": Decimal("5.0"),
        "r_over_atr": Decimal("5.0"),
    }

    downtrend_candles = [c_open] + [
        make_candle(
            i,
            str(2700 - i * 10),
            str(2705 - i * 10),
            str(2685 - i * 10),
            str(2690 - i * 10),
        )
        for i in range(1, 30)
    ]
    res = engine.run(downtrend_candles)
    assert not engine.exchange.has_open_position()
    assert res.total_trades > 0


def test_backtest_tp2_execution_for_runner() -> None:
    """Backtest engine executes TP2 at final_tp_ratio (3.0R) for remaining runner after TP1."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    exit_mgr = ExitManager(
        partial_tp_ratio=Decimal("1.5"),
        final_tp_ratio=Decimal("3.0"),
        enable_partial_tp=True,
    )
    cfg = BacktestConfig(user_risk_config=user_risk)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    engine = BacktestEngine(config=cfg, exit_manager=exit_mgr, estimator=estimator)

    # Entry at 2700, stop at 2680 -> R = 20.00.
    # TP1 (1.5R) = 2730.00. TP2 (3.0R) = 2760.00.
    c1 = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("2700.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1080.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    trade = engine.exchange.process_order(intent, c1)
    assert trade is not None
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "STRONG_BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.00"),
        "initial_r": Decimal("20.00"),
        "configured_risk": Decimal("10.00"),
        "theoretical_risk": Decimal("10.00"),
        "actual_risk": Decimal("10.00"),
        "actual_risk_pct": Decimal("1.0"),
        "atr_at_entry": Decimal("5.0"),
        "r_over_atr": Decimal("4.0"),
    }

    # Candle 2 hits TP1 (high = 2732 >= 2730)
    c2 = make_candle(1, "2710.0", "2732.0", "2708.0", "2730.0")
    # Candle 3 reaches TP2 (high = 2762 >= 2760)
    c3 = make_candle(2, "2730.0", "2765.0", "2728.0", "2760.0")

    res = engine.run([c1, c2, c3])
    # Position should be completely closed via TP1 + TP2
    assert not engine.exchange.has_open_position()
    assert res.winning_trades > 0


def test_backtest_max_holding_hours_exit() -> None:
    """Backtest engine exits open position when holding time exceeds max_holding_hours."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
        max_holding_time_hours=2,  # 2 hours = 8 candles on 15M
    )
    exit_mgr = ExitManager(max_holding_hours=2)
    cfg = BacktestConfig(user_risk_config=user_risk)
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    engine = BacktestEngine(config=cfg, exit_manager=exit_mgr, estimator=estimator)

    c0 = make_candle(0, "2700.0", "2705.0", "2695.0", "2700.0")
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("2700.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1080.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    trade = engine.exchange.process_order(intent, c0)
    assert trade is not None
    engine.active_trade_meta[trade.trade_id] = {
        "entry_score": Decimal("85.0"),
        "regime": "STRONG_BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2650.00"),
        "initial_r": Decimal("50.00"),
        "configured_risk": Decimal("10.00"),
        "theoretical_risk": Decimal("10.00"),
        "actual_risk": Decimal("10.00"),
        "actual_risk_pct": Decimal("1.0"),
        "atr_at_entry": Decimal("5.0"),
        "r_over_atr": Decimal("10.0"),
    }

    # Feed 10 candles where price stays flat (no stop or TP hit)
    flat_candles = [c0] + [
        make_candle(i, "2700.0", "2702.0", "2698.0", "2700.0") for i in range(1, 12)
    ]
    res = engine.run(flat_candles)
    # The trade should have been closed due to time exit
    assert not engine.exchange.has_open_position()
    assert res.total_trades > 0
    time_exits = [
        t
        for t in engine.exchange.closed_trades
        if t.exit_reason and "Max holding time" in t.exit_reason
    ]
    assert len(time_exits) > 0
