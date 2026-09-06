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
