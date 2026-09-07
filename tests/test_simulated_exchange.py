"""Tests for SimulatedExchange in event-driven backtesting."""

from decimal import Decimal

import pytest

from src.backtest.exchange import SimulatedExchange
from src.backtest.models import BacktestConfig
from src.config.settings import UserRiskConfig
from src.domain.enums import OrderSide, Timeframe
from src.domain.models import Candle, OrderIntent


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


def make_candle(
    open_p: str, high_p: str, low_p: str, close_p: str, t: int = 1700000000000
) -> Candle:
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


def test_simulated_exchange_fill_and_fee(backtest_config: BacktestConfig) -> None:
    """Order within candle range fills, charges taker fee, and creates open position."""
    exchange = SimulatedExchange(config=backtest_config)
    candle = make_candle("2700.00", "2710.00", "2690.00", "2705.00")

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_BUY_1",
        reason="Entry test",
    )

    trade = exchange.process_order(intent, candle)
    assert trade is not None
    assert exchange.has_open_position() is True
    assert exchange.position is not None
    assert exchange.position.size == Decimal("1.0")
    # Fee paid in Decimal
    assert exchange.total_fees_paid > Decimal("0")


def test_simulated_exchange_liquidation(backtest_config: BacktestConfig) -> None:
    """If candle touches liquidation price, position is liquidated with explicit model."""
    from src.risk.liquidation import ConfigurableLiquidationEstimator

    estimator = ConfigurableLiquidationEstimator(fixed_price=Decimal("2160.00"))
    exchange = SimulatedExchange(config=backtest_config, estimator=estimator)
    candle_entry = make_candle("2700.00", "2710.00", "2695.00", "2700.00", t=1700000000000)

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_BUY_LIQ",
        reason="Entry test",
    )
    exchange.process_order(intent, candle_entry)
    assert exchange.position is not None
    assert exchange.position.liquidation_price == Decimal("2160.00")

    # Candle dipping to 2100 (below estimated liquidation at 2160)
    candle_crash = make_candle("2300.00", "2300.00", "2100.00", "2150.00", t=1700000900000)
    was_liquidated = exchange.check_liquidation(candle_crash)

    assert was_liquidated is True
    assert exchange.has_open_position() is False
    assert exchange.liquidations_count == 1


def test_simulated_exchange_no_liquidation_when_unavailable(
    backtest_config: BacktestConfig,
) -> None:
    """When liquidation estimator is unavailable, liquidation_price is None and no liquidation."""
    from src.backtest.models import LiquidationModelPolicy

    policy = backtest_config.execution_policy.model_copy(
        update={"liquidation_policy": LiquidationModelPolicy.UNAVAILABLE}
    )
    cfg = backtest_config.model_copy(update={"execution_policy": policy})
    exchange = SimulatedExchange(config=cfg, estimator=None)
    candle_entry = make_candle("2700.00", "2710.00", "2695.00", "2700.00", t=1700000000000)

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_BUY_UNAVAIL",
        reason="Entry test",
    )
    exchange.process_order(intent, candle_entry)
    assert exchange.position is not None
    assert exchange.position.liquidation_price is None

    # Even on a massive crash, liquidation cannot trigger from a fabricated price
    candle_crash = make_candle("2300.00", "2300.00", "1000.00", "1100.00", t=1700000900000)
    assert exchange.check_liquidation(candle_crash) is False
    assert exchange.has_open_position() is True
    assert exchange.liquidations_count == 0


def test_simulated_exchange_funding_accrual(backtest_config: BacktestConfig) -> None:
    """Funding payment is debited/credited every 8 hours."""
    exchange = SimulatedExchange(config=backtest_config)
    candle = make_candle("2700.00", "2710.00", "2690.00", "2705.00")

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="TEST_BUY_FUNDING",
        reason="Entry test",
    )
    exchange.process_order(intent, candle)

    # 8-hour timestamp interval with 0.01% positive funding rate (long pays)
    exchange.apply_funding(
        timestamp=1700000000000 + 28800000,
        funding_rate=Decimal("0.0001"),
    )
    assert exchange.total_funding_paid > Decimal("0")


def test_simulated_exchange_dca_addition(backtest_config: BacktestConfig) -> None:
    """DCA addition updates position size and average entry price."""
    exchange = SimulatedExchange(config=backtest_config)
    candle1 = make_candle("2700.00", "2710.00", "2690.00", "2700.00")
    intent1 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("0.100"),
        price=Decimal("2700.00"),
        notional=Decimal("270.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_INIT",
        reason="Initial entry",
    )
    exchange.process_order(intent1, candle1)

    # DCA order at 2650
    candle2 = make_candle("2660.00", "2670.00", "2640.00", "2650.00")
    intent2 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("0.100"),
        price=Decimal("2650.00"),
        notional=Decimal("265.00"),
        is_dca=True,
        is_opening=True,
        client_order_id="BUY_DCA",
        reason="DCA entry",
    )
    trade_dca = exchange.process_order(intent2, candle2)
    assert trade_dca is not None
    assert exchange.position is not None
    assert exchange.position.size == Decimal("0.200")
    assert exchange.position.entry_price < Decimal("2700.00")


def test_simulated_exchange_sell_full_and_partial(backtest_config: BacktestConfig) -> None:
    """SELL order executes partial or full exit and tracks realized P&L and excursions."""
    exchange = SimulatedExchange(config=backtest_config)
    candle1 = make_candle("2700.00", "2710.00", "2690.00", "2700.00")
    intent_buy = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_FOR_SELL",
        reason="Entry",
    )
    exchange.process_order(intent_buy, candle1)

    # Update excursions on high candle
    candle2 = make_candle("2700.00", "2750.00", "2680.00", "2740.00")
    exchange.update_excursions(candle2)
    assert exchange.active_trade is not None
    assert exchange.active_trade.max_favorable_excursion > Decimal("0")
    assert exchange.active_trade.max_adverse_excursion > Decimal("0")

    # Partial SELL limit at 2730
    intent_sell_partial = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.5"),
        price=Decimal("2730.00"),
        notional=Decimal("1365.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="SELL_PARTIAL",
        reason="Partial TP",
    )
    exchange.process_order(intent_sell_partial, candle2)
    assert exchange.has_open_position()
    assert exchange.position is not None
    assert exchange.position.size == Decimal("0.5")

    # Limit SELL at 2800 cannot fill if candle high < 2800
    candle3 = make_candle("2740.00", "2760.00", "2730.00", "2750.00")
    intent_unfillable = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.5"),
        price=Decimal("2800.00"),
        notional=Decimal("1400.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="SELL_UNFILLABLE",
        reason="Unfillable TP",
    )
    res = exchange.process_order(intent_unfillable, candle3)
    assert res is None
    assert exchange.position.size == Decimal("0.5")

    # Full exit market order
    intent_full = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="MARKET",
        quantity=Decimal("0.5"),
        price=Decimal("2750.00"),
        notional=Decimal("1375.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="SELL_FULL",
        reason="Full exit",
    )
    exchange.process_order(intent_full, candle3)
    assert not exchange.has_open_position()
    assert len(exchange.closed_trades) == 1
    assert exchange.closed_trades[0].realized_pnl > Decimal("0")


def test_zero_maker_fee_configuration(backtest_config: BacktestConfig) -> None:
    """Verify that maker fee can be configured to zero and executes with 0 fee paid."""
    from src.backtest.models import BacktestExecutionPolicy, FeeProfile
    from src.domain.enums import LiquidityRole

    fee_profile = FeeProfile(
        profile_name="ZERO_MAKER_PROMO",
        maker_fee=Decimal("0.0"),
        taker_fee=Decimal("0.0005"),
        is_assumed=True,
    )
    policy = BacktestExecutionPolicy(fee_profile=fee_profile)
    config = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        user_risk_config=backtest_config.user_risk_config,
        execution_policy=policy,
    )
    exchange = SimulatedExchange(config=config)

    # Passive limit buy below candle open (open = 2700, limit buy = 2695)
    candle = make_candle("2700.00", "2705.00", "2690.00", "2700.00")
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2695.00"),
        notional=Decimal("2695.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="PASSIVE_BUY",
        reason="Entry",
    )
    role = exchange.determine_liquidity_role(intent, candle)
    assert role == LiquidityRole.MAKER

    trade = exchange.process_order(intent, candle)
    assert trade is not None
    assert trade.maker_fees_paid == Decimal("0.0")
    assert trade.fees_paid == Decimal("0.0")
    assert exchange.total_fees_paid == Decimal("0.0")
    assert exchange.total_maker_fees_paid == Decimal("0.0")


def test_marketable_limit_classified_as_taker(backtest_config: BacktestConfig) -> None:
    """Verify that a Limit Buy with price >= candle.open is classified as TAKER."""
    from src.domain.enums import LiquidityRole

    exchange = SimulatedExchange(config=backtest_config)
    candle = make_candle("2700.00", "2710.00", "2695.00", "2705.00")

    # Limit Buy at 2702 (>= open 2700.00) crosses the spread immediately
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        quantity=Decimal("1.0"),
        price=Decimal("2702.00"),
        notional=Decimal("2702.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="MARKETABLE_BUY",
        reason="Marketable entry",
    )
    role = exchange.determine_liquidity_role(intent, candle)
    assert role == LiquidityRole.TAKER

    trade = exchange.process_order(intent, candle)
    assert trade is not None
    assert trade.taker_fees_paid > Decimal("0.0")
    assert trade.maker_fees_paid == Decimal("0.0")
    assert exchange.total_taker_fees_paid > Decimal("0.0")


def test_funding_settlement_direction_and_size_invariance(backtest_config: BacktestConfig) -> None:
    """Verify funding direction (debit for positive, credit for negative)
    and partial/DCA settlement.
    """
    exchange = SimulatedExchange(config=backtest_config)
    candle0 = make_candle("2700.00", "2705.00", "2695.00", "2700.00")

    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("1.0"),
        price=Decimal("2700.00"),
        notional=Decimal("2700.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="BUY_FUNDING_TEST",
        reason="Entry",
    )
    exchange.process_order(intent, candle0)
    assert exchange.active_trade is not None
    init_balance = exchange.wallet_balance

    # 1. Positive funding debits wallet balance on long position
    # notional = 1.0 * 2700.27 (after slippage)
    pos_notional = exchange.position.size * exchange.position.entry_price  # type: ignore
    exchange.apply_funding(1700000000000, funding_rate=Decimal("0.0001"))
    expected_debit = pos_notional * Decimal("0.0001")
    assert exchange.wallet_balance == init_balance - expected_debit
    assert exchange.active_trade.funding_paid == expected_debit

    # 2. Negative funding credits wallet balance on long position
    bal_before_credit = exchange.wallet_balance
    exchange.apply_funding(1700028800000, funding_rate=Decimal("-0.0001"))
    expected_credit = pos_notional * Decimal("-0.0001")
    assert exchange.wallet_balance == bal_before_credit - expected_credit

    # 3. Partial exit before funding: funding is charged only on remaining size
    candle1 = make_candle("2720.00", "2725.00", "2715.00", "2720.00")
    intent_partial = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.5"),
        price=Decimal("2720.00"),
        notional=Decimal("1360.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="PARTIAL_EXIT",
        reason="TP",
    )
    exchange.process_order(intent_partial, candle1)
    assert exchange.position.size == Decimal("0.5")  # type: ignore

    bal_before_part = exchange.wallet_balance
    exchange.apply_funding(1700057600000, funding_rate=Decimal("0.0002"))
    remaining_notional = Decimal("0.5") * exchange.position.entry_price  # type: ignore
    assert exchange.wallet_balance == bal_before_part - (remaining_notional * Decimal("0.0002"))

    # 4. Complete exit: no funding charged after position closed
    intent_close = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="MARKET",
        quantity=Decimal("0.5"),
        price=Decimal("2720.00"),
        notional=Decimal("1360.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="FULL_EXIT",
        reason="Close",
    )
    exchange.process_order(intent_close, candle1)
    assert not exchange.has_open_position()

    bal_after_close = exchange.wallet_balance
    exchange.apply_funding(1700086400000, funding_rate=Decimal("0.0005"))
    # Wallet balance must remain completely unchanged when flat
    assert exchange.wallet_balance == bal_after_close


def test_multi_fill_accounting_consistency(backtest_config: BacktestConfig) -> None:
    """Verify that multi-fill lifecycle (Entry -> DCA -> Partial TP -> Full Close)
    maintains 0 remaining inventory and exact P&L.
    """
    exchange = SimulatedExchange(config=backtest_config)
    c0 = make_candle("2700.00", "2710.00", "2690.00", "2700.00")

    # 1. Entry: 0.200 XAU @ 2700
    i1 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("0.200"),
        price=Decimal("2700.00"),
        notional=Decimal("540.00"),
        is_dca=False,
        is_opening=True,
        client_order_id="E1",
        reason="Entry",
    )
    exchange.process_order(i1, c0)

    # 2. DCA: 0.100 XAU @ 2680
    c1 = make_candle("2680.00", "2690.00", "2675.00", "2680.00")
    i2 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        quantity=Decimal("0.100"),
        price=Decimal("2680.00"),
        notional=Decimal("268.00"),
        is_dca=True,
        is_opening=True,
        client_order_id="DCA1",
        reason="DCA",
    )
    exchange.process_order(i2, c1)
    assert exchange.position.size == Decimal("0.300")  # type: ignore

    # 3. Partial TP: 0.150 XAU @ 2720
    c2 = make_candle("2720.00", "2730.00", "2710.00", "2720.00")
    i3 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        quantity=Decimal("0.150"),
        price=Decimal("2720.00"),
        notional=Decimal("408.00"),
        is_dca=False,
        is_opening=False,
        client_order_id="TP1",
        reason="Partial TP",
    )
    exchange.process_order(i3, c2)
    assert exchange.position.size == Decimal("0.150")  # type: ignore

    # 4. Final Close: 0.150 XAU @ 2710
    c3 = make_candle("2710.00", "2715.00", "2700.00", "2710.00")
    i4 = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="MARKET",
        quantity=Decimal("0.150"),
        price=Decimal("2710.00"),
        notional=Decimal("406.50"),
        is_dca=False,
        is_opening=False,
        client_order_id="EXIT1",
        reason="Final Exit",
    )
    exchange.process_order(i4, c3)

    # Invariant: zero remaining position
    assert not exchange.has_open_position()
    assert exchange.position is None
    assert len(exchange.closed_trades) == 1
    t = exchange.closed_trades[0]
    assert t.fees_paid == t.maker_fees_paid + t.taker_fees_paid
