"""TDD tests for trustworthy backtest execution, causal ATR, intrabar ambiguity, and accounting."""

from decimal import Decimal

import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.exchange import SimulatedExchange
from src.backtest.models import (
    BacktestConfig,
    BacktestExecutionPolicy,
    IntrabarAmbiguityPolicy,
    LiquidationModelPolicy,
    SimulatedTrade,
)
from src.config.settings import UserRiskConfig
from src.domain.enums import OrderSide, Timeframe
from src.domain.models import Candle, OrderIntent
from src.exchange.metadata import SymbolFilters
from src.risk.engine import RiskEngine
from src.risk.liquidation import (
    ConfigurableLiquidationEstimator,
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


def test_default_backtest_engine_fails_closed_when_liquidation_unavailable(
    base_risk_config: UserRiskConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without an explicit margin estimator, BacktestEngine defaults to Unavailable.

    Ensures no false claims of 100% liquidation safety without exchange margin tiers.
    """
    from unittest.mock import MagicMock

    from src.domain.enums import DecisionState, MarketRegime
    from src.domain.models import DecisionSnapshot
    from src.strategy.entry_families import EntryFamily, EntrySetup

    cfg = BacktestConfig(user_risk_config=base_risk_config)
    mock_strat = MagicMock()
    mock_strat.evaluate.return_value = DecisionSnapshot(
        decision_id="mock_buy",
        symbol="XAUUSDT",
        timestamp=1700000000000,
        decision_state=DecisionState.BUY,
        regime=MarketRegime.STRONG_BULL,
        reason="Mock confluence buy",
    )
    engine = BacktestEngine(config=cfg, strategy_engine=mock_strat)
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

    candles = [
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000 + i * 900000,
            open=Decimal("2700.0"),
            high=Decimal("2710.0"),
            low=Decimal("2690.0"),
            close=Decimal("2705.0"),
            volume=Decimal("100.0"),
            close_time=1700000000000 + (i + 1) * 900000 - 1,
            is_closed=True,
        )
        for i in range(25)
    ]
    result = engine.run(candles)
    # Zero trades entered because liquidation safety is strictly UNAVAILABLE
    assert result.total_trades == 0
    assert result.net_profit == Decimal("0.0")


def test_execution_policy_single_source_of_truth(base_risk_config: UserRiskConfig) -> None:
    """BacktestConfig routes fees and slippage directly into BacktestExecutionPolicy."""
    cfg1 = BacktestConfig(
        user_risk_config=base_risk_config,
        maker_fee=Decimal("0.0003"),
        taker_fee=Decimal("0.0007"),
        slippage_pct=Decimal("0.0002"),
    )
    assert cfg1.execution_policy.maker_fee == Decimal("0.0003")
    assert cfg1.execution_policy.taker_fee == Decimal("0.0007")
    assert cfg1.execution_policy.slippage_pct == Decimal("0.0002")
    assert cfg1.maker_fee == Decimal("0.0003")
    assert cfg1.taker_fee == Decimal("0.0007")
    assert cfg1.slippage_pct == Decimal("0.0002")


def test_execution_policy_fees_and_slippage_directly_affect_exchange(
    base_risk_config: UserRiskConfig,
) -> None:
    """Higher configured fees in execution_policy directly increase total_fees_paid."""
    low_fee_policy = BacktestExecutionPolicy(
        maker_fee=Decimal("0.0001"),
        taker_fee=Decimal("0.0002"),
        slippage_pct=Decimal("0.0"),
    )
    high_fee_policy = BacktestExecutionPolicy(
        maker_fee=Decimal("0.0010"),
        taker_fee=Decimal("0.0020"),
        slippage_pct=Decimal("0.0005"),
    )

    cfg_low = BacktestConfig(user_risk_config=base_risk_config, execution_policy=low_fee_policy)
    cfg_high = BacktestConfig(user_risk_config=base_risk_config, execution_policy=high_fee_policy)

    exchange_low = SimulatedExchange(config=cfg_low)
    exchange_high = SimulatedExchange(config=cfg_high)

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
    market_buy = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="MARKET",
        price=Decimal("4000.00"),
        quantity=Decimal("1.000"),
        notional=Decimal("4000.00"),
        client_order_id="BUY_FEE_TEST",
        reason="Test",
    )

    exchange_low.process_order(market_buy, candle)
    exchange_high.process_order(market_buy, candle)

    assert exchange_high.total_fees_paid > exchange_low.total_fees_paid
    # High slippage means higher fill price for buy order
    assert exchange_high.position is not None and exchange_low.position is not None
    assert exchange_high.position.entry_price > exchange_low.position.entry_price


def test_performance_breakdowns_populated_correctly(
    base_risk_config: UserRiskConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Backtest engine correctly partitions trades by setup family, regime, and score bucket."""
    from unittest.mock import MagicMock

    from src.domain.enums import DecisionState, MarketRegime
    from src.domain.models import DecisionSnapshot
    from src.risk.liquidation import ConfigurableLiquidationEstimator, LiquidationSafetyStatus
    from src.strategy.entry_families import EntryFamily, EntrySetup

    estimator = ConfigurableLiquidationEstimator(
        fixed_price=Decimal("2400.00"),
        forced_status=LiquidationSafetyStatus.SAFE,
    )
    cfg = BacktestConfig(user_risk_config=base_risk_config)
    mock_strat = MagicMock()
    mock_strat.evaluate.return_value = DecisionSnapshot(
        decision_id="mock_buy",
        symbol="XAUUSDT",
        timestamp=1700000000000,
        decision_state=DecisionState.BUY,
        regime=MarketRegime.STRONG_BULL,
        reason="Mock confluence buy",
    )
    engine = BacktestEngine(config=cfg, strategy_engine=mock_strat, estimator=estimator)
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

    candles = [
        Candle(
            symbol="XAUUSDT",
            timeframe=Timeframe.M15,
            open_time=1700000000000 + i * 900000,
            open=Decimal("2700.0"),
            high=Decimal("2710.0"),
            low=Decimal("2690.0"),
            close=Decimal("2705.0"),
            volume=Decimal("100.0"),
            close_time=1700000000000 + (i + 1) * 900000 - 1,
            is_closed=True,
        )
        for i in range(25)
    ]
    result = engine.run(candles)
    assert result.total_trades > 0

    # Breakdowns must be populated
    assert "TREND_PULLBACK" in result.setup_family_performance
    assert len(result.regime_performance) >= 1
    assert any(k in result.regime_performance for k in ["NEUTRAL", "BULL", "STRONG_BULL"])
    assert "85-89" in result.score_bucket_performance

    fam_perf = result.setup_family_performance["TREND_PULLBACK"]
    assert "total_trades" in fam_perf
    assert "win_rate" in fam_perf
    assert "net_pnl" in fam_perf
    assert "profit_factor" in fam_perf
    assert fam_perf["total_trades"] == Decimal(str(result.total_trades))


def test_insufficient_bars_handles_atr_unavailability(base_risk_config: UserRiskConfig) -> None:
    """When candle count is < 15, trailing stop does not activate on fabricated ATR."""
    engine = BacktestEngine(config=BacktestConfig(user_risk_config=base_risk_config))
    candle = Candle(
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
    # resolve_intrabar_exit with current_atr=None should safely return None without crashing
    exit_intent, is_ambiguous = engine.resolve_intrabar_exit(
        candle=candle,
        entry_price=Decimal("4000.00"),
        stop_loss=Decimal("3980.00"),
        take_profit=Decimal("4050.00"),
        highest_price=Decimal("4010.00"),
        current_atr=None,
    )
    assert exit_intent is None
    assert is_ambiguous is False


def test_simulated_exchange_refuses_to_fabricate_liquidation_price(
    base_risk_config: UserRiskConfig,
) -> None:
    """SimulatedExchange strictly never fabricates liquidation prices without explicit estimator."""
    # When estimator is not provided or policy is UNAVAILABLE, liquidation_price is None
    cfg = BacktestConfig(
        user_risk_config=base_risk_config,
        execution_policy=BacktestExecutionPolicy(
            liquidation_policy=LiquidationModelPolicy.UNAVAILABLE
        ),
    )
    exchange = SimulatedExchange(config=cfg, estimator=None)
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("2700.00"),
        high=Decimal("2710.00"),
        low=Decimal("2690.00"),
        close=Decimal("2700.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        price=Decimal("2700.00"),
        quantity=Decimal("1.000"),
        notional=Decimal("2700.00"),
        is_opening=True,
        client_order_id="BUY_1",
        reason="Entry",
    )
    exchange.process_order(intent, candle)
    assert exchange.position is not None
    # Invariant: No generic formula (such as 2700 * (1 - 1/2) = 1350) fabricated!
    assert exchange.position.liquidation_price is None


def test_simulated_exchange_uses_explicit_estimator_when_injected(
    base_risk_config: UserRiskConfig,
) -> None:
    """When EXPLICIT_MODEL policy and estimator are provided, SimulatedExchange uses estimator."""
    estimator = ConfigurableLiquidationEstimator(fixed_price=Decimal("2450.00"))
    cfg = BacktestConfig(
        user_risk_config=base_risk_config,
        execution_policy=BacktestExecutionPolicy(
            liquidation_policy=LiquidationModelPolicy.EXPLICIT_MODEL
        ),
    )
    exchange = SimulatedExchange(config=cfg, estimator=estimator)
    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("2700.00"),
        high=Decimal("2710.00"),
        low=Decimal("2690.00"),
        close=Decimal("2700.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    intent = OrderIntent(
        symbol="XAUUSDT",
        side=OrderSide.BUY,
        order_type="LIMIT",
        price=Decimal("2700.00"),
        quantity=Decimal("1.000"),
        notional=Decimal("2700.00"),
        is_opening=True,
        client_order_id="BUY_EXPLICIT",
        reason="Entry",
    )
    exchange.process_order(intent, candle)
    assert exchange.position is not None
    assert exchange.position.liquidation_price == Decimal("2450.00")


def test_backtest_missing_initial_stop_metadata_fails_closed(
    base_risk_config: UserRiskConfig,
) -> None:
    """If trade metadata lacks authoritative initial_stop/initial_r, engine raises ValueError."""
    cfg = BacktestConfig(user_risk_config=base_risk_config)
    engine = BacktestEngine(config=cfg)

    # Manually append a simulated trade without recording active_trade_meta
    trade = SimulatedTrade(
        trade_id="missing_meta_1",
        entry_time=1000,
        exit_time=2000,
        entry_price=Decimal("2700.00"),
        exit_price=Decimal("2710.00"),
        size=Decimal("1.000"),
        notional=Decimal("2700.00"),
        realized_pnl=Decimal("10.00"),
        exit_reason="TP",
    )
    engine.exchange.closed_trades.append(trade)

    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=5000,
        open=Decimal("2700.00"),
        high=Decimal("2705.00"),
        low=Decimal("2695.00"),
        close=Decimal("2700.00"),
        volume=Decimal("10.0"),
        close_time=5999,
        is_closed=True,
    )
    with pytest.raises(ValueError, match="missing authoritative initial_stop"):
        engine.run([candle])


def test_causal_mfe_and_r_analytics_math(base_risk_config: UserRiskConfig) -> None:
    """Verify mathematical correctness of MFE, MAE, R multiples, hit rates, and surrendered R."""
    cfg = BacktestConfig(user_risk_config=base_risk_config)
    engine = BacktestEngine(config=cfg)

    # Setup 2 closed trades with known MFE, MAE, and PnL
    # Trade 1: Entry 2700, Stop 2680 (Risk 20), Size 1.0. MFE $40 (2.0R), Exit 2730 (+30, 1.5R).
    t1 = SimulatedTrade(
        trade_id="t1",
        entry_time=1000,
        exit_time=2000,
        entry_price=Decimal("2700.00"),
        exit_price=Decimal("2730.00"),
        size=Decimal("1.000"),
        notional=Decimal("2700.00"),
        realized_pnl=Decimal("30.00"),
        max_favorable_excursion=Decimal("40.00"),
        max_adverse_excursion=Decimal("5.00"),
        exit_reason="TP",
    )
    # Trade 2: Entry 2700, Stop 2680 (Risk 20), Size 1.0. MFE $10 (0.5R), Exit 2680 (-20, -1.0R).
    t2 = SimulatedTrade(
        trade_id="t2",
        entry_time=3000,
        exit_time=4000,
        entry_price=Decimal("2700.00"),
        exit_price=Decimal("2680.00"),
        size=Decimal("1.000"),
        notional=Decimal("2700.00"),
        realized_pnl=Decimal("-20.00"),
        max_favorable_excursion=Decimal("10.00"),
        max_adverse_excursion=Decimal("20.00"),
        exit_reason="STOP",
    )
    engine.exchange.closed_trades.extend([t1, t2])
    engine.active_trade_meta["t1"] = {
        "entry_score": Decimal("85.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.00"),
        "initial_r": Decimal("20.00"),
    }
    engine.active_trade_meta["t2"] = {
        "entry_score": Decimal("82.0"),
        "regime": "BULL",
        "entry_family": "TREND_PULLBACK",
        "initial_stop": Decimal("2680.00"),
        "initial_r": Decimal("20.00"),
    }

    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=5000,
        open=Decimal("2700.00"),
        high=Decimal("2705.00"),
        low=Decimal("2695.00"),
        close=Decimal("2700.00"),
        volume=Decimal("10.0"),
        close_time=5999,
        is_closed=True,
    )
    res = engine.run([candle])
    assert res.total_trades == 2
    assert res.winning_trades == 1
    assert res.losing_trades == 1

    # Diagnostics inspection
    assert len(res.diagnostics) == 2
    d1 = res.diagnostics[0]
    assert d1.mfe == Decimal("40.00")
    assert d1.mfe_r == Decimal("2.00")
    assert d1.realized_r == Decimal("1.50")

    d2 = res.diagnostics[1]
    assert d2.mfe == Decimal("10.00")
    assert d2.mfe_r == Decimal("0.50")
    assert d2.realized_r == Decimal("-1.00")

    # MFE / R summary metrics
    # mfe_avg: (40 + 10) / 2 = 25.00
    assert res.mfe_avg == Decimal("25.00")
    # mfe_median: median([40, 10]) = 25.00
    assert res.mfe_median == Decimal("25.00")
    # mfe_r_avg: (2.0 + 0.5) / 2 = 1.25
    assert res.mfe_r_avg == Decimal("1.25")
    # max_r_reached: 2.00
    assert res.max_r_reached == Decimal("2.00")
    # r_realized_avg: (1.50 - 1.00) / 2 = 0.25
    assert res.r_realized_avg == Decimal("0.25")
    # r_surrendered_avg:
    # t1 surrendered: 2.0 - 1.5 = 0.5R
    # t2 surrendered: 0.5 - (-1.0) = 1.5R
    # avg surrendered: (0.5 + 1.5) / 2 = 1.00R
    assert res.r_surrendered_avg == Decimal("1.00")

    # mfe_realization_pct_winners: t1 realized 30/40 * 100 = 75.0%
    assert res.mfe_realization_pct_winners == Decimal("75.00")

    # Target R hit rates
    assert res.r_target_hit_rates["0.5R"] == Decimal("1.00")  # both reached >= 0.5R
    assert res.r_target_hit_rates["1.0R"] == Decimal("0.50")  # only t1 reached >= 1.0R
    assert res.r_target_hit_rates["1.5R"] == Decimal("0.50")
    assert res.r_target_hit_rates["2.0R"] == Decimal("0.50")

    # Positive MFE closing loser: t2 had MFE 10.00 but lost -> 1 out of 2 = 50.0%
    assert res.positive_mfe_closing_loser_pct == Decimal("50.00")

    # Liquidation status is explicitly UNAVAILABLE, never false 100% safe claim
    assert res.liquidation_model_status == "UNAVAILABLE"
    assert res.liquidations_count == 0


def test_partial_exit_preserves_mfe_mae_r_accounting(
    base_risk_config: UserRiskConfig,
) -> None:
    """When partial TP is taken, active trade continues tracking MFE/MAE accurately."""
    cfg = BacktestConfig(
        user_risk_config=base_risk_config,
        execution_policy=BacktestExecutionPolicy(
            slippage_pct=Decimal("0.0"), taker_fee=Decimal("0.0"), maker_fee=Decimal("0.0")
        ),
    )
    exchange = SimulatedExchange(config=cfg)

    # Initial entry: 1.0 @ 2700
    c1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1000,
        open=Decimal("2700.00"),
        high=Decimal("2710.00"),
        low=Decimal("2695.00"),
        close=Decimal("2700.00"),
        volume=Decimal("10.0"),
        close_time=1999,
        is_closed=True,
    )
    exchange.process_order(
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.BUY,
            order_type="LIMIT",
            price=Decimal("2700.00"),
            quantity=Decimal("1.000"),
            notional=Decimal("2700.00"),
            is_opening=True,
            client_order_id="BUY_INIT",
            reason="Entry",
        ),
        c1,
    )

    # Price moves up: High 2740 (favorable = (2740 - 2700) * 1.0 = 40.0)
    c2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=2000,
        open=Decimal("2710.00"),
        high=Decimal("2740.00"),
        low=Decimal("2705.00"),
        close=Decimal("2730.00"),
        volume=Decimal("10.0"),
        close_time=2999,
        is_closed=True,
    )
    exchange.update_excursions(c2)
    assert exchange.active_trade is not None
    assert exchange.active_trade.max_favorable_excursion == Decimal("40.00")

    # Partial TP at 2730 for 0.5 size
    exchange.process_order(
        OrderIntent(
            symbol="XAUUSDT",
            side=OrderSide.SELL,
            order_type="LIMIT",
            price=Decimal("2730.00"),
            quantity=Decimal("0.500"),
            notional=Decimal("1365.00"),
            is_opening=False,
            client_order_id="PARTIAL_TP",
            reason="Partial TP",
        ),
        c2,
    )
    assert exchange.active_trade.max_favorable_excursion == Decimal("40.00")
    assert exchange.active_trade.realized_pnl == Decimal("15.00")  # (2730 - 2700) * 0.5

    # Candle dips lower: low 2680 (adverse excursion on 0.5 pos: (2700 - 2680) * 0.5 = 10.0)
    c3 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=3000,
        open=Decimal("2710.00"),
        high=Decimal("2715.00"),
        low=Decimal("2680.00"),
        close=Decimal("2690.00"),
        volume=Decimal("10.0"),
        close_time=3999,
        is_closed=True,
    )
    exchange.update_excursions(c3)
    assert exchange.active_trade.max_adverse_excursion == Decimal("10.00")
