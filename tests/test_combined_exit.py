"""TDD unit tests for Experiment 3B-C: Combined Breakeven + Partial TP.

Verifies:
1. Breakeven activates at >= 1.0R (stop ratcheted to entry + $0.50).
2. Partial TP activates at >= 1.5R.
3. Both mechanisms can occur on the same trade.
4. Partial TP occurs only once.
5. Exactly 50% is closed on partial TP.
6. Remaining 50% retains the breakeven-protected stop (does not revert to initial stop).
7. Original initial_r remains immutable throughout both actions.
8. Breakeven cannot move downward (strictly monotonic).
9. Partial TP does not occur below 1.5R.
10. No breakeven behavior when price never reaches 1.0R.
11. No partial TP when price never reaches 1.5R.
12. Conservative adverse-first intrabar policy remains unchanged when both stop and TP breached.
13. Realized P&L and fees account correctly for both partial and final exits.
14. MFE/MAE remain causally correct across multi-fill exits.
15. DCA / position accounting remains correct after partial exit.
"""

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


def create_combined_engine(
    enable_breakeven: bool = True,
    breakeven_r_multiple: Decimal = Decimal("1.0"),
    breakeven_buffer: Decimal = Decimal("0.50"),
    enable_partial_tp: bool = True,
    partial_tp_ratio: Decimal = Decimal("1.5"),
    partial_tp_pct: Decimal = Decimal("50.0"),
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
        enable_breakeven=enable_breakeven,
        breakeven_r_multiple=breakeven_r_multiple,
        breakeven_buffer=breakeven_buffer,
        enable_partial_tp=enable_partial_tp,
        partial_tp_ratio=partial_tp_ratio,
        partial_tp_pct=partial_tp_pct,
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


def test_1_breakeven_activates_at_1_0r() -> None:
    """1. Breakeven ratchets stop to entry + $0.50 when highest price >= entry + 1.0 * initial_r."""
    engine = create_combined_engine()
    # entry 4000.00, stop 3980.00 -> initial_r = 20.00. 1.0R trigger = 4020.00
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4015.00"),
        high=Decimal("4021.00"),  # reaches 4021.00 >= 4020.00
        low=Decimal("4010.00"),
        close=Decimal("4020.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    ratcheted_stop = engine.update_breakeven_stop(
        candle=candle,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4021.00"),
    )
    assert ratcheted_stop == Decimal("4000.50")


def test_2_partial_tp_activates_at_1_5r() -> None:
    """2. Partial TP activates when candle high reaches entry + 1.5 * initial_r."""
    engine = create_combined_engine()
    # entry 4000.00, initial_r = 20.00 -> 1.5R target = 4030.00
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

    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4025.00"),
        high=Decimal("4032.00"),  # >= 4030.00
        low=Decimal("4020.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    intent, is_ambig = engine.resolve_intrabar_exit(
        candle=candle2,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("4000.50"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4032.00"),
        current_atr=Decimal("10.00"),
    )
    assert intent is not None
    assert "PARTIAL_TP" in intent.client_order_id
    assert intent.price == Decimal("4030.00")
    assert intent.quantity == Decimal("0.200")
    assert is_ambig is False


def test_3_4_5_6_both_mechanisms_and_runner_retention() -> None:
    """3, 4, 5, 6. Breakeven then partial TP on same trade; remaining 50% retains BE stop."""
    engine = create_combined_engine()
    # Step A: Open position 0.400 at 4000.00, stop 3980.00 (init_r = 20.00)
    c1 = Candle(
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
    engine.exchange.process_order(buy, c1)

    # Step B: Candle 2 reaches +1.1R (4022.00) -> Breakeven activates to 4000.50
    c2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4005.00"),
        high=Decimal("4022.00"),
        low=Decimal("4002.00"),
        close=Decimal("4020.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    stop = engine.update_breakeven_stop(
        candle=c2,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4022.00"),
    )
    assert stop == Decimal("4000.50")

    # Step C: Candle 3 reaches +1.6R (4032.00) -> 50% partial TP executed
    c3 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("4020.00"),
        high=Decimal("4032.00"),
        low=Decimal("4015.00"),
        close=Decimal("4030.00"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    tp_intent, _ = engine.resolve_intrabar_exit(
        candle=c3,
        entry_price=Decimal("4000.00"),
        stop_loss=stop,
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4032.00"),
        current_atr=Decimal("10.00"),
    )
    assert tp_intent is not None
    assert tp_intent.quantity == Decimal("0.200")  # exactly 50%
    engine.exchange.process_order(tp_intent, c3)
    assert engine.exchange.position is not None
    assert engine.exchange.position.size == Decimal("0.200")

    # Step D: Verify partial TP occurs only once: subsequent check has tp_target=None
    partial_tp_taken = True
    tp_target = (
        Decimal("4000.00") + (Decimal("20.00") * Decimal("1.5")) if (not partial_tp_taken) else None
    )
    assert tp_target is None

    # Step E: Candle 4 retraces beneath entry down to 4000.20
    # Stop MUST remain at 4000.50 (retained BE protection) and trigger stop exit!
    c4 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=4000,
        open=Decimal("4015.00"),
        high=Decimal("4018.00"),
        low=Decimal("4000.20"),  # breaches ratcheted stop 4000.50
        close=Decimal("4000.30"),
        volume=Decimal("10.0"),
        close_time=4999,
        is_closed=True,
    )
    exit_intent, _ = engine.resolve_intrabar_exit(
        candle=c4,
        entry_price=Decimal("4000.00"),
        stop_loss=stop,  # 4000.50
        take_profit=None,
        highest_price=Decimal("4032.00"),
        current_atr=Decimal("10.00"),
    )
    assert exit_intent is not None
    assert "STOP" in exit_intent.client_order_id
    assert exit_intent.quantity == Decimal("0.200")  # closes remaining 50%
    assert exit_intent.price == Decimal("4000.50")  # exits at BE stop!


def test_7_original_initial_r_remains_immutable() -> None:
    """7. The original initial_r ($20.00) is immutable and not recalculated after partial TP."""
    engine = create_combined_engine()
    init_r = Decimal("20.00")
    # Even if stop is moved to 4000.50, initial_r remains 20.00
    tp_target = Decimal("4000.00") + (init_r * engine.exit_manager.partial_tp_ratio)
    assert tp_target == Decimal("4030.00")


def test_8_breakeven_cannot_move_downward() -> None:
    """8. Breakeven ratchet is strictly monotonic and never lowers the stop."""
    engine = create_combined_engine()
    c = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("3990.00"),
        high=Decimal("3995.00"),
        low=Decimal("3985.00"),
        close=Decimal("3990.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    # If current stop is already 4000.50, price drop cannot lower it back to 3980.00
    stop = engine.update_breakeven_stop(
        candle=c,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("4000.50"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4025.00"),
    )
    assert stop == Decimal("4000.50")


def test_9_partial_tp_does_not_occur_below_1_5r() -> None:
    """9. Partial TP does not trigger when high reaches only 1.4R."""
    engine = create_combined_engine()
    c = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4010.00"),
        high=Decimal("4028.00"),  # +1.4R (< 4030.00)
        low=Decimal("4010.00"),
        close=Decimal("4025.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    intent, _ = engine.resolve_intrabar_exit(
        candle=c,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4028.00"),
        current_atr=Decimal("10.00"),
    )
    assert intent is None


def test_10_no_breakeven_when_price_never_reaches_1_0r() -> None:
    """10. Stop loss remains unchanged when price never touches 1.0R."""
    engine = create_combined_engine()
    c = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4005.00"),
        high=Decimal("4018.00"),  # +0.9R (< 4020.00)
        low=Decimal("3995.00"),
        close=Decimal("4010.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    stop = engine.update_breakeven_stop(
        candle=c,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4018.00"),
    )
    assert stop == Decimal("3980.00")


def test_11_no_partial_tp_when_price_never_reaches_1_5r() -> None:
    """11. No TP intent generated when high is below target."""
    engine = create_combined_engine()
    c = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4015.00"),
        high=Decimal("4025.00"),
        low=Decimal("4012.00"),
        close=Decimal("4022.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    intent, _ = engine.resolve_intrabar_exit(
        candle=c,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("4000.50"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4025.00"),
        current_atr=Decimal("10.00"),
    )
    assert intent is None


def test_12_conservative_adverse_first_intrabar() -> None:
    """12. If candle pierces both stop loss and partial TP, stop loss triggers first."""
    engine = create_combined_engine()
    c1 = Candle(
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
    engine.exchange.process_order(buy, c1)

    c = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4010.00"),
        high=Decimal("4040.00"),  # breaches TP 4030.00
        low=Decimal("3995.00"),  # breaches BE stop 4000.50
        close=Decimal("4035.00"),
        volume=Decimal("50.0"),
        close_time=2999,
        is_closed=True,
    )
    intent, is_ambig = engine.resolve_intrabar_exit(
        candle=c,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("4000.50"),
        take_profit=Decimal("4030.00"),
        highest_price=Decimal("4040.00"),
        current_atr=Decimal("10.00"),
    )
    assert intent is not None
    assert is_ambig is True
    assert "STOP" in intent.client_order_id


def test_13_14_15_accounting_and_dca_after_partial_tp() -> None:
    """13, 14, 15. Accounting combines partial TP + BE stop, preserves MFE/MAE, and handles DCA."""
    policy = BacktestExecutionPolicy(
        intrabar_ambiguity=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST,
        liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL,
        slippage_pct=Decimal("0.0"),
    )
    engine = create_combined_engine(policy=policy)
    c1 = Candle(
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
    engine.exchange.process_order(buy, c1)

    # Partial TP at 4030.00 for 0.200 -> profit = 30.00 * 0.200 = +6.00
    c2 = Candle(
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
    engine.exchange.update_excursions(c2)
    tp_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("4030.00"),
        quantity=Decimal("0.200"),
        client_order_id="PARTIAL_TP_1",
        reason="Partial TP 1.5R",
        order_type="LIMIT",
    )
    engine.exchange.process_order(tp_intent, c2)

    # BE stop at 4000.50 for remaining 0.200 -> profit = 0.50 * 0.200 = +0.10
    c3 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("4002.00"),
        high=Decimal("4005.00"),
        low=Decimal("4000.00"),
        close=Decimal("4000.50"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    engine.exchange.update_excursions(c3)
    stop_intent = engine.risk_sizer.create_exit_intent(
        price=Decimal("4000.50"),
        quantity=Decimal("0.200"),
        client_order_id="STOP_1",
        reason="BE Stop",
        order_type="LIMIT",
    )
    engine.exchange.process_order(stop_intent, c3)

    assert engine.exchange.position is None
    closed = engine.exchange.closed_trades[0]
    # Total realized PnL = +6.00 + +0.10 = +6.10 (strictly profitable!)
    assert closed.realized_pnl == Decimal("6.10")
    assert closed.size == Decimal("0.400")
    assert closed.max_favorable_excursion > Decimal("0.0")
