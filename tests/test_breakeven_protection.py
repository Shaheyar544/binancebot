"""TDD tests for Causal +1.0R Breakeven Stop-Loss Protection."""

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


def create_test_engine(
    enable_breakeven: bool = True,
    breakeven_r: Decimal = Decimal("1.0"),
    breakeven_buffer: Decimal = Decimal("0.50"),
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
    policy = BacktestExecutionPolicy(
        intrabar_ambiguity=IntrabarAmbiguityPolicy.CONSERVATIVE_ADVERSE_FIRST,
        liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL,
    )
    cfg = BacktestConfig(
        initial_balance=Decimal("10000.00"),
        user_risk_config=risk_config,
        execution_policy=policy,
    )
    exit_mgr = ExitManager(
        enable_breakeven=enable_breakeven,
        breakeven_r_multiple=breakeven_r,
        breakeven_buffer=breakeven_buffer,
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


def test_breakeven_not_triggered_when_mfe_below_1r() -> None:
    """Stop remains at initial stop loss if peak favorable price has not reached +1.0R."""
    engine = create_test_engine(enable_breakeven=True, breakeven_r=Decimal("1.0"))

    # Entry at 4000.00, stop at 3980.00 -> initial R = 20.00
    candle1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("4000.00"),
        high=Decimal("4010.00"),  # reaches +0.5R (+10.00)
        low=Decimal("3995.00"),
        close=Decimal("4005.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
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
    engine.active_trade_meta["BUY_TEST"] = {
        "initial_stop": Decimal("3980.00"),
        "initial_r": Decimal("20.00"),
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
    }

    # Candle 2 reaches 4015.00 (+0.75R), not 1.0R (4020.00)
    candle2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4005.00"),
        high=Decimal("4015.00"),
        low=Decimal("3990.00"),
        close=Decimal("4000.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    stop = engine.update_breakeven_stop(
        candle=candle2,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4015.00"),
    )
    assert stop == Decimal("3980.00")


def test_breakeven_triggered_at_or_above_1r() -> None:
    """Stop ratchets up to entry_price + buffer when highest price reaches +1.0R."""
    engine = create_test_engine(
        enable_breakeven=True,
        breakeven_r=Decimal("1.0"),
        breakeven_buffer=Decimal("0.50"),
    )

    # Entry at 4000.00, stop at 3980.00 -> initial R = 20.00. 1.0R target is 4020.00
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("4005.00"),
        high=Decimal("4021.00"),  # reaches > 1.0R
        low=Decimal("3990.00"),
        close=Decimal("4015.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    stop = engine.update_breakeven_stop(
        candle=candle,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("3980.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4021.00"),
    )
    # Stop should move to entry (4000.00) + buffer (0.50) = 4000.50
    assert stop == Decimal("4000.50")


def test_breakeven_stop_never_moves_backward() -> None:
    """Ratcheted breakeven stop is strictly monotonic and never lowers."""
    engine = create_test_engine(
        enable_breakeven=True,
        breakeven_r=Decimal("1.0"),
        breakeven_buffer=Decimal("0.50"),
    )

    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("4010.00"),
        high=Decimal("4012.00"),
        low=Decimal("4002.00"),
        close=Decimal("4003.00"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    # Current stop already at 4005.00 (e.g. from trailing)
    stop = engine.update_breakeven_stop(
        candle=candle,
        entry_price=Decimal("4000.00"),
        current_stop=Decimal("4005.00"),
        initial_r=Decimal("20.00"),
        highest_price=Decimal("4025.00"),
    )
    assert stop == Decimal("4005.00")
