"""Tests for StrategyEngine end-to-end candidate decision generation and gating."""

from decimal import Decimal

from src.analysis.models import MultiTimeframeAnalysis, TimeframeAnalysis
from src.domain.enums import DecisionState, MarketRegime, Timeframe
from src.market_data.enums import MarketDataHealth
from src.strategy.engine import StrategyEngine


def make_tf_analysis(
    timeframe: Timeframe,
    is_bullish: bool,
    close_price: Decimal = Decimal("2750.0"),
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=timeframe,
        is_bullish=is_bullish,
        current_close=close_price,
        ema_10=Decimal("2740.0") if is_bullish else Decimal("2760.0"),
        ema_20=Decimal("2730.0") if is_bullish else Decimal("2770.0"),
        ema_50=Decimal("2710.0") if is_bullish else Decimal("2780.0"),
        ema_200=Decimal("2650.0") if is_bullish else Decimal("2800.0"),
        rsi=Decimal("58.0") if is_bullish else Decimal("42.0"),
        atr=Decimal("15.0"),
        volume_ratio=Decimal("1.5") if is_bullish else Decimal("0.8"),
    )


def test_high_conviction_bullish_produces_buy() -> None:
    """When all multi-timeframe conditions align and score >= 85, produce BUY."""
    engine = StrategyEngine(min_entry_score=85)
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )

    assert decision.decision_state == DecisionState.BUY
    assert decision.regime == MarketRegime.STRONG_BULL
    assert "score" in decision.reason.lower()


def test_bearish_htf_structure_blocks_entry() -> None:
    """If 1D or 4H structure is bearish, new LONG entries must be BLOCKED."""
    engine = StrategyEngine(min_entry_score=85)
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.NEUTRAL,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=False),  # 1D is Bearish!
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )

    assert decision.decision_state == DecisionState.BLOCKED
    assert "Higher-timeframe structure is bearish" in decision.reason


def test_unsafe_market_data_produces_data_unsafe() -> None:
    """When market data health is not HEALTHY, engine returns DATA_UNSAFE."""
    engine = StrategyEngine()
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.GAP_DETECTED,
        has_setup=True,
        favorable_rr=True,
    )

    assert decision.decision_state == DecisionState.DATA_UNSAFE
    assert "Market data health is unsafe" in decision.reason


def test_insufficient_score_produces_wait() -> None:
    """When setup exists but score is below 85, produce WAIT."""
    engine = StrategyEngine(min_entry_score=85)
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.BULLISH_RANGE,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=False),  # Missing 1H confirmation
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=False,
    )

    assert decision.decision_state == DecisionState.WAIT
    assert "Score below entry threshold" in decision.reason


def test_hostile_regime_blocks_entry() -> None:
    """When market regime is BEAR or STRONG_BEAR, strategy engine blocks long entries."""
    engine = StrategyEngine(min_entry_score=85)
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BEAR,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )

    assert decision.decision_state == DecisionState.BLOCKED
    assert "hostile to long entries" in decision.reason


def test_event_risk_regime_enforces_news_lock() -> None:
    """When market regime is EVENT_RISK, strategy engine returns NEWS_LOCK."""
    engine = StrategyEngine()
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.EVENT_RISK,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )

    assert decision.decision_state == DecisionState.NEWS_LOCK
    assert "news lock enforced" in decision.reason


def test_strategy_engine_with_gradient_scoring() -> None:
    """StrategyEngine works seamlessly with use_gradient_scoring=True."""
    engine = StrategyEngine(min_entry_score=85)
    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=make_tf_analysis(Timeframe.D1, is_bullish=True),
        analysis_4h=make_tf_analysis(Timeframe.H4, is_bullish=True),
        analysis_1h=make_tf_analysis(Timeframe.H1, is_bullish=True),
        analysis_15m=make_tf_analysis(Timeframe.M15, is_bullish=True),
        timestamp=1700000900000,
    )

    decision = engine.evaluate(
        mtf=mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
        use_gradient_scoring=True,
    )
    assert decision.decision_state == DecisionState.BUY
    assert "High conviction bullish setup" in decision.reason


def test_exit_manager_structural_stop_loss() -> None:
    """ExitManager triggers EXIT immediately when price drops below stop loss reference."""
    from src.strategy.engine import ExitManager

    exit_mgr = ExitManager()
    decision = exit_mgr.evaluate_position(
        current_price=Decimal("2680.00"),
        entry_price=Decimal("2700.00"),
        stop_loss_ref=Decimal("2685.00"),  # Breached!
        atr=Decimal("10.00"),
        highest_price_since_entry=Decimal("2705.00"),
        entry_timestamp=1000,
        current_timestamp=2000,
    )
    assert decision.should_exit is True
    assert decision.exit_state == DecisionState.EXIT
    assert "Stop loss reference breached" in decision.reason
    assert decision.portion_pct == Decimal("100.0")


def test_exit_manager_partial_take_profit() -> None:
    """ExitManager triggers PARTIAL_TP when price reaches configured R multiple."""
    from src.strategy.engine import ExitManager

    exit_mgr = ExitManager(partial_tp_ratio=Decimal("1.5"), partial_tp_pct=Decimal("50.0"))
    # Risk = 2700 - 2690 = 10. Target = 2700 + 15 = 2715
    decision = exit_mgr.evaluate_position(
        current_price=Decimal("2716.00"),
        entry_price=Decimal("2700.00"),
        stop_loss_ref=Decimal("2690.00"),
        atr=Decimal("10.00"),
        highest_price_since_entry=Decimal("2716.00"),
        entry_timestamp=1000,
        current_timestamp=2000,
        partial_tp_already_taken=False,
    )
    assert decision.should_exit is True
    assert decision.exit_state == DecisionState.PARTIAL_TP
    assert "Partial TP reached" in decision.reason
    assert decision.portion_pct == Decimal("50.0")


def test_exit_manager_trailing_stop() -> None:
    """ExitManager triggers trailing stop when price retreats from high after moving into profit."""
    from src.strategy.engine import ExitManager

    exit_mgr = ExitManager(trailing_atr_multiplier=Decimal("1.5"))
    # Highest was 2740, ATR is 10 -> Trailing stop = 2740 - 15 = 2725 (above entry of 2700)
    decision = exit_mgr.evaluate_position(
        current_price=Decimal("2724.00"),  # Dips below 2725
        entry_price=Decimal("2700.00"),
        stop_loss_ref=Decimal("2690.00"),
        atr=Decimal("10.00"),
        highest_price_since_entry=Decimal("2740.00"),
        entry_timestamp=1000,
        current_timestamp=2000,
        partial_tp_already_taken=True,
    )
    assert decision.should_exit is True
    assert decision.exit_state == DecisionState.EXIT
    assert "Trailing stop breached" in decision.reason
    assert decision.portion_pct == Decimal("100.0")
