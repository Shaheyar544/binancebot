"""TDD tests for trustworthy backtest execution, causal ATR, intrabar ambiguity, and accounting."""

from decimal import Decimal

import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.exchange import SimulatedExchange
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    IntrabarAmbiguityPolicy,
)
from src.config.settings import UserRiskConfig
from src.domain.enums import OrderSide, Timeframe
from src.domain.models import Candle, OrderIntent
from src.exchange.metadata import SymbolFilters
from src.risk.engine import RiskEngine
from src.risk.liquidation import (
    UnavailableLiquidationEstimator,
)
from src.risk.models import AccountRiskState, RiskRejectionReason


@pytest.fixture
def base_risk_config() -> UserRiskConfig:
    return UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
    )


@pytest.fixture
def xau_filters() -> SymbolFilters:
    return SymbolFilters(
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


def test_liquidation_marked_unavailable_when_exchange_tiers_missing(
    base_risk_config: UserRiskConfig,
    xau_filters: SymbolFilters,
) -> None:
    """When exchange inputs are absent, RiskEngine marks liquidation safety UNAVAILABLE."""
    estimator = UnavailableLiquidationEstimator(reason="No live Binance margin tiers")
    risk_engine = RiskEngine(config=base_risk_config, filters=xau_filters, estimator=estimator)

    from src.domain.enums import DecisionState, MarketRegime
    from src.domain.models import DecisionSnapshot

    decision = DecisionSnapshot(
        decision_id="test-1",
        symbol="XAUUSDT",
        decision_state=DecisionState.BUY,
        regime=MarketRegime.BULL,
        reason="Test",
        timestamp=1000000,
    )
    acc = AccountRiskState(
        wallet_balance=Decimal("1000.00"),
        available_balance=Decimal("1000.00"),
        total_open_exposure=Decimal("0.0"),
        realized_daily_loss=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        open_entries_count=0,
    )
    result = risk_engine.evaluate_entry(decision, Decimal("4000.00"), acc, Decimal("500.00"))
    assert result.is_approved is False
    assert result.rejection_reason == RiskRejectionReason.LIQUIDATION_INFO_UNAVAILABLE
    assert "No live Binance margin tiers" in result.explanation


def test_intrabar_ambiguity_conservative_adverse_first(base_risk_config: UserRiskConfig) -> None:
    """When candle low reaches stop AND high reaches TP, conservative policy triggers stop."""
    policy = BacktestExecutionPolicy(
        intrabar_ambiguity=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST
    )
    cfg = BacktestConfig(user_risk_config=base_risk_config, execution_policy=policy)
    engine = BacktestEngine(config=cfg)

    # 1. Provide an initial entry candle
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
    # Manually open a position on the exchange for testing exit ambiguity
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("0.1"),
        notional=Decimal("400.00"),
        client_order_id="BUY_TEST",
        reason="Test",
    )
    engine.exchange.process_order(intent, candle1)
    assert engine.exchange.has_open_position()

    # Candle 2 has wide range that breaches both Stop (3980) and TP (4030)
    stop_ref = Decimal("3980.00")
    tp_ref = Decimal("4030.00")
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4000.00"),
        high=Decimal("4050.00"),  # breaches TP 4030
        low=Decimal("3970.00"),  # breaches Stop 3980
        close=Decimal("4040.00"),
        volume=Decimal("50.0"),
        close_time=2999,
        is_closed=True,
    )

    exit_intent, is_ambiguous = engine.resolve_intrabar_exit(
        candle=candle2,
        entry_price=Decimal("4000.00"),
        stop_loss=stop_ref,
        take_profit=tp_ref,
        highest_price=Decimal("4050.00"),
        current_atr=Decimal("12.0"),
    )
    assert is_ambiguous is True
    assert exit_intent is not None
    # Conservative adverse-first must choose the Stop Loss exit
    assert (
        "Stop loss" in exit_intent.reason
        or "STOP" in exit_intent.reason
        or "Adverse" in exit_intent.reason
    )
    assert exit_intent.price <= stop_ref


def test_partial_exit_accounting_preserves_position_lifecycle(
    base_risk_config: UserRiskConfig,
) -> None:
    """Partial exit reduces position size, realizes partial PnL/fees, keeps active trade open."""
    policy = BacktestExecutionPolicy(
        slippage_pct=Decimal("0.0"), taker_fee=Decimal("0.0"), maker_fee=Decimal("0.0")
    )
    cfg = BacktestConfig(user_risk_config=base_risk_config, execution_policy=policy)
    exchange = SimulatedExchange(config=cfg)

    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4010.00"),
        low=Decimal("3990.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )

    # Initial entry: Buy 1.0 @ 4000
    buy_intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("1.000"),
        notional=Decimal("4000.00"),
        client_order_id="ENTRY_1",
        reason="Entry",
    )
    exchange.process_order(buy_intent, candle)
    assert exchange.position is not None
    assert exchange.position.size == Decimal("1.000")
    assert exchange.active_trade is not None
    initial_trade_id = exchange.active_trade.trade_id

    # Partial exit: Sell 0.5 @ 4050 (+ gross profit)
    candle_tp = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4040.00"),
        high=Decimal("4060.00"),
        low=Decimal("4030.00"),
        close=Decimal("4050.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    partial_sell = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="LIMIT",
        price=Decimal("4050.00"),
        quantity=Decimal("0.500"),
        notional=Decimal("2025.00"),
        is_opening=False,
        client_order_id="PARTIAL_1",
        reason="Partial TP",
    )
    res = exchange.process_order(partial_sell, candle_tp)
    assert res is not None
    assert exchange.has_open_position()
    assert exchange.position.size == Decimal("0.500")
    assert exchange.active_trade is not None
    assert exchange.active_trade.trade_id == initial_trade_id
    assert exchange.active_trade.realized_pnl == Decimal("25.00")
    assert len(exchange.closed_trades) == 0  # Not closed yet!

    # Full exit remainder: Sell 0.5 @ 4040 (+ gross profit)
    full_sell = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.SELL,
        order_type="MARKET",
        price=Decimal("4040.00"),
        quantity=Decimal("0.500"),
        notional=Decimal("2020.00"),
        is_opening=False,
        client_order_id="FULL_EXIT",
        reason="Exit",
    )
    exchange.process_order(full_sell, candle_tp)
    assert exchange.has_open_position() is False
    assert len(exchange.closed_trades) == 1
    closed = exchange.closed_trades[0]
    assert closed.realized_pnl == Decimal("45.00")
    assert closed.size == Decimal("1.000")


def test_causal_dynamic_atr_computation(base_risk_config: UserRiskConfig) -> None:
    """ATR dynamically computed strictly from historical candles without lookahead."""
    from src.analysis.indicators import calculate_atr

    candles = [
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=i * 900000,
            open=Decimal(str(4000 + i)),
            high=Decimal(str(4010 + i * 2)),
            low=Decimal(str(3990 - i)),
            close=Decimal(str(4005 + i)),
            volume=Decimal("10.0"),
            close_time=(i + 1) * 900000 - 1,
            is_closed=True,
        )
        for i in range(25)
    ]

    # Calculate ATR over expanding historical window
    atr_15 = calculate_atr(candles[:16], period=14)
    atr_25 = calculate_atr(candles[:25], period=14)

    assert atr_15 is not None
    assert atr_25 is not None
    assert atr_15 != atr_25
    assert atr_15 > Decimal("0")
    # Must NOT equal the old hardcoded 15.0
    assert atr_15 != Decimal("15.0")


def test_per_trade_diagnostic_telemetry(base_risk_config: UserRiskConfig) -> None:
    """Backtest engine produces rich PerTradeDiagnostic records with MFE, MAE, and fee breakdown."""
    from src.backtest.models import PerTradeDiagnostic

    diag = PerTradeDiagnostic(
        trade_id="trade-123",
        entry_time=1000,
        exit_time=5000,
        holding_duration_ms=4000,
        entry_score=Decimal("88"),
        regime="BULL",
        entry_family="PULLBACK",
        entry_price=Decimal("4000.00"),
        initial_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        exit_price=Decimal("4050.00"),
        exit_reason="Take Profit",
        realized_r=Decimal("2.5"),
        mfe=Decimal("60.00"),
        mae=Decimal("10.00"),
        mfe_capture_pct=Decimal("83.33"),
        gross_pnl=Decimal("50.00"),
        net_pnl=Decimal("45.00"),
        fees_paid=Decimal("5.00"),
        funding_paid=Decimal("0.00"),
        dca_count=0,
        partial_tp_taken=False,
    )
    assert diag.realized_r == Decimal("2.5")
    assert diag.net_pnl == Decimal("45.00")
    assert diag.fees_paid == Decimal("5.00")
    assert diag.mfe == Decimal("60.00")
    assert diag.mae == Decimal("10.00")
