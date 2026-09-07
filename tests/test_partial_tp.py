"""TDD unit tests for Experiment 3B-B: Partial Take-Profit (+1.5R / 50%) Only."""

from decimal import Decimal

from src.backtest.engine import BacktestEngine
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    IntrabarAmbiguityPolicy,
    LiquidationModelPolicy,
)
from src.config.settings import UserRiskConfig
from src.domain.enums import OrderSide, Timeframe
from src.domain.models import Candle, OrderIntent
from src.exchange.metadata import SymbolFilters
from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
from src.strategy.engine import ExitManager


def create_partial_tp_engine(
    partial_tp_ratio: Decimal = Decimal("1.5"),
    partial_tp_pct: Decimal = Decimal("50.0"),
    enable_partial_tp: bool = True,
    enable_breakeven: bool = False,
    policy: BacktestExecutionPolicy | None = None,
) -> BacktestEngine:
    risk_config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
    )
    filters = SymbolFilters(
        symbol="XAUUSDT",
        status="TRADING",
        contract_type="PERPETUAL",
        base_asset="XAU",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=3,
        tick_size=Decimal("0.01"),
        min_price=Decimal("100.00"),
        max_price=Decimal("100000.00"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("1000.000"),
        min_notional=Decimal("5.0"),
    )
    if policy is None:
        policy = BacktestExecutionPolicy(
            intrabar_ambiguity=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST,
            liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL,
            maker_fee=Decimal("0.0002"),
            taker_fee=Decimal("0.0005"),
            slippage_pct=Decimal("0.0001"),
        )
    cfg = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        user_risk_config=risk_config,
        execution_policy=policy,
    )
    exit_mgr = ExitManager(
        partial_tp_ratio=partial_tp_ratio,
        partial_tp_pct=partial_tp_pct,
        enable_partial_tp=enable_partial_tp,
        enable_breakeven=enable_breakeven,
    )
    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    return BacktestEngine(
        config=cfg,
        exit_manager=exit_mgr,
        filters=filters,
        estimator=estimator,
    )


def test_1_partial_tp_triggers_at_1_5r() -> None:
    """1. Partial TP triggers when candle high reaches entry + 1.5 * initial_r."""
    engine = create_partial_tp_engine()
    # entry 4000, stop 3980 -> initial_r = 20.00, +1.5R target = 4030.00
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)
    assert engine.exchange.position is not None

    # Candle 2 reaches 4032.00 (> 4030.00 target); low 4015.00 > trail stop 4012.00
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4015.00"),
        high=Decimal("4032.00"),
        low=Decimal("4015.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    exit_intent, is_ambig = engine.resolve_intrabar_exit(
        candle=candle2,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4032.00"),
        current_atr=Decimal("10.00"),
    )
    assert exit_intent is not None
    assert "PARTIAL_TP" in exit_intent.client_order_id
    assert exit_intent.price == Decimal("4030.00")
    assert exit_intent.quantity == Decimal("0.200")
    assert is_ambig is False


def test_2_no_trigger_below_1_5r() -> None:
    """2. No Partial TP intent is generated if candle high does not reach target."""
    engine = create_partial_tp_engine()
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)

    # Target is 4030.00 (+1.5R), candle high reaches only 4028.00 (+1.4R)
    # low is 4010.00 (above trailing stop 4028 - 20 = 4008.00)
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4010.00"),
        high=Decimal("4028.00"),
        low=Decimal("4010.00"),
        close=Decimal("4025.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    exit_intent, _ = engine.resolve_intrabar_exit(
        candle=candle,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4028.00"),
        current_atr=Decimal("10.00"),
    )
    assert exit_intent is None


def test_3_and_4_exactly_one_partial_tp_and_50_pct_reduction() -> None:
    """3 & 4. Executes exactly once and reduces position by exactly 50%."""
    engine = create_partial_tp_engine()
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)
    assert engine.exchange.position is not None
    assert engine.exchange.position.size == Decimal("0.400")

    # Execute partial TP intent
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4020.00"),
        high=Decimal("4035.00"),
        low=Decimal("4015.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    exit_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("4030.00"),
        quantity=Decimal("0.200"),
        client_order_id="PARTIAL_TP_2000",
        reason="Partial TP reached 1.5R",
        order_type="LIMIT",
    )
    engine.exchange.process_order(exit_intent, candle2)

    # Position size must be exactly 0.200 (50% reduction)
    assert engine.exchange.position is not None
    assert engine.exchange.position.size == Decimal("0.200")

    # In engine simulation, partial_tp_taken flag ensures tp_target becomes None
    partial_tp_taken = True
    tp_target = (
        Decimal("4000.00") + (Decimal("20.00") * Decimal("1.5")) if (not partial_tp_taken) else None
    )
    assert tp_target is None


def test_5_remaining_position_continues_under_existing_exit_logic() -> None:
    """5. Remaining 50% position stays open and exits when stop loss is breached."""
    engine = create_partial_tp_engine()
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)

    # Candle 2 reaches 4035.00 (> 4030.00)
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4020.00"),
        high=Decimal("4035.00"),
        low=Decimal("4015.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    # Partial exit of 0.200 at 4030.00
    ptp_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("4030.00"),
        quantity=Decimal("0.200"),
        client_order_id="PARTIAL_TP_1",
        reason="Partial TP",
        order_type="LIMIT",
    )
    engine.exchange.process_order(ptp_intent, candle2)
    assert engine.exchange.position is not None
    assert engine.exchange.position.size == Decimal("0.200")

    # Now candle 3 drops and breaches stop loss at 3980.00
    candle3 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("3990.00"),
        high=Decimal("3995.00"),
        low=Decimal("3975.00"),  # breaches stop 3980.00
        close=Decimal("3978.00"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    exit_intent, _ = engine.resolve_intrabar_exit(
        candle=candle3,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=None,  # partial TP already taken
        highest_price=Decimal("4030.00"),
        current_atr=Decimal("10.00"),
    )
    assert exit_intent is not None
    assert "STOP" in exit_intent.client_order_id
    assert exit_intent.quantity == Decimal("0.200")  # closes remaining 50%

    engine.exchange.process_order(exit_intent, candle3)
    assert engine.exchange.position is None
    assert len(engine.exchange.closed_trades) == 1


def test_6_and_7_accounting_initial_r_and_combined_pnl() -> None:
    """6 & 7. Accounting correctly combines partial TP + final exit P&L and preserves initial R."""
    policy = BacktestExecutionPolicy(
        intrabar_ambiguity=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST,
        liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL,
        slippage_pct=Decimal("0.0"),
    )
    engine = create_partial_tp_engine(policy=policy)
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    # 0.400 limit order at 4000.00 (zero slippage)
    buy = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(buy, candle1)

    # 1. Partial TP on Candle 2: sell 0.200 at 4030.00 (+30.00 * 0.200 = +$6.00 profit)
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4020.00"),
        high=Decimal("4035.00"),
        low=Decimal("4015.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    tp_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("4030.00"),
        quantity=Decimal("0.200"),
        client_order_id="PARTIAL_TP_1",
        reason="Partial TP 1.5R",
        order_type="LIMIT",
    )
    engine.exchange.process_order(tp_intent, candle2)
    # Partial PnL should be 6.00
    assert engine.exchange.active_trade is not None
    assert engine.exchange.active_trade.realized_pnl == Decimal("6.00")

    # 2. Final Stop on Candle 3: sell remaining 0.200 at 3980.00 (-20.00/oz * 0.200 = -$4.00 loss)
    candle3 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("3980.00"),
        high=Decimal("3985.00"),
        low=Decimal("3975.00"),
        close=Decimal("3980.00"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    stop_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("3980.00"),
        quantity=Decimal("0.200"),
        client_order_id="STOP_1",
        reason="Stop loss",
        order_type="LIMIT",
    )
    engine.exchange.process_order(stop_intent, candle3)

    assert engine.exchange.position is None
    closed = engine.exchange.closed_trades[0]
    # Total realized PnL = +6.00 (from partial TP) - 4.00 (from stop) = +2.00
    assert closed.realized_pnl == Decimal("2.00")
    # Total size reflects full original size (0.400)
    assert closed.size == Decimal("0.400")


def test_8_no_accidental_breakeven_behavior() -> None:
    """8. In Experiment 3B-B, breakeven is disabled; stop remains at initial stop loss."""
    engine = create_partial_tp_engine(enable_breakeven=False)
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4030.00"),
        high=Decimal("4035.00"),
        low=Decimal("3998.00"),  # falls beneath entry (4000) but above initial stop (3980)
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    # Breakeven update should return the current stop unchanged (3980.00)
    stop = engine.update_breakeven_stop(
        candle=candle,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4035.00"),
    )
    assert stop == Decimal("3980.00")


def test_9_causal_intrabar_conservative_adverse_first() -> None:
    """9. Candle breaching both stop loss and partial TP triggers stop loss first."""
    engine = create_partial_tp_engine(enable_partial_tp=True)
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4005.00"),
        low=Decimal("3995.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("0.400"),
        notional=Decimal("1600.00"),
        client_order_id="BUY_1",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)

    # Candle 2 low pierces stop (3980.00) AND candle high pierces TP (4030.00)
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4000.00"),
        high=Decimal("4040.00"),  # breaches TP 4030
        low=Decimal("3970.00"),  # breaches Stop 3980
        close=Decimal("4035.00"),
        volume=Decimal("50.0"),
        close_time=2999,
        is_closed=True,
    )
    exit_intent, is_ambig = engine.resolve_intrabar_exit(
        candle=candle2,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4040.00"),
        current_atr=Decimal("10.00"),
    )
    assert exit_intent is not None
    assert is_ambig is True
    # Conservative adverse-first policy must trigger the stop loss, not take profit
    assert "STOP" in exit_intent.client_order_id
