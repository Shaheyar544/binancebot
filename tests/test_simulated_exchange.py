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
    """If candle low touches liquidation price, position is liquidated."""
    exchange = SimulatedExchange(config=backtest_config)
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

    # Candle dipping to 2100 (below estimated liquidation at 2160)
    candle_crash = make_candle("2300.00", "2300.00", "2100.00", "2150.00", t=1700000900000)
    was_liquidated = exchange.check_liquidation(candle_crash)

    assert was_liquidated is True
    assert exchange.has_open_position() is False
    assert exchange.liquidations_count == 1


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
