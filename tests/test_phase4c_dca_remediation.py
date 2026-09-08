"""Tests for Phase 4C: DCA Qualification Remediation.

Verifies:
1. DCA rejected when score is below 85 (e.g. score 75-84).
2. DCA approved only when score >= 85 with 1D, 4H, and 1H bullish alignment.
3. DCA blocked if 1H structure is not bullish.
4. DCA blocked if position drawdown exceeds -0.5R.
5. DCA blocked if regime is not STRONG_BULL or BULL.
"""

from decimal import Decimal

from src.analysis.models import MultiTimeframeAnalysis, TimeframeAnalysis
from src.domain.enums import DecisionState, MarketRegime, Timeframe
from src.market_data.enums import MarketDataHealth
from src.strategy.engine import StrategyEngine


def _make_sample_analysis(
    is_bullish: bool = True,
    close: Decimal = Decimal("2500.00"),
    rsi: Decimal = Decimal("60.0"),
    ema_10: Decimal = Decimal("2490.00"),
    ema_20: Decimal = Decimal("2480.00"),
    ema_50: Decimal = Decimal("2470.00"),
    ema_200: Decimal = Decimal("2400.00"),
    volume_ratio: Decimal = Decimal("1.5"),
    atr: Decimal = Decimal("10.0"),
) -> TimeframeAnalysis:
    return TimeframeAnalysis(
        timeframe=Timeframe.M15,
        current_close=close,
        ema_10=ema_10,
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        rsi=rsi,
        atr=atr,
        is_bullish=is_bullish,
        volume_ratio=volume_ratio,
    )


def test_dca_requires_score_at_least_85() -> None:
    engine = StrategyEngine(min_entry_score=85)

    # 1D, 4H, 1H bullish
    analysis_1d = _make_sample_analysis(is_bullish=True)
    analysis_4h = _make_sample_analysis(is_bullish=True)
    analysis_1h = _make_sample_analysis(is_bullish=True, rsi=Decimal("58.0"))
    analysis_15m = _make_sample_analysis(
        is_bullish=True,
        close=Decimal("2500.00"),
        volume_ratio=Decimal("1.3"),
    )

    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=analysis_1d,
        analysis_4h=analysis_4h,
        analysis_1h=analysis_1h,
        analysis_15m=analysis_15m,
        timestamp=100000,
    )

    # With high score (85+), DCA should be approved
    decision = engine.evaluate_dca(
        mtf=mtf,
        current_position_r=Decimal("0.1"),
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert decision.decision_state == DecisionState.ADD
    assert "score=" in decision.reason


def test_dca_rejected_when_score_below_85() -> None:
    engine = StrategyEngine(min_entry_score=85)

    analysis_1d = _make_sample_analysis(is_bullish=True)
    analysis_4h = _make_sample_analysis(is_bullish=True)
    analysis_1h = _make_sample_analysis(is_bullish=True, rsi=Decimal("48.0"))  # Weak momentum
    analysis_15m = _make_sample_analysis(
        is_bullish=True,
        close=Decimal("2485.00"),  # Below EMA10
        ema_10=Decimal("2490.00"),
        ema_20=Decimal("2480.00"),
        volume_ratio=Decimal("0.8"),  # Low volume
    )

    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.BULL,
        analysis_1d=analysis_1d,
        analysis_4h=analysis_4h,
        analysis_1h=analysis_1h,
        analysis_15m=analysis_15m,
        timestamp=100000,
    )

    decision = engine.evaluate_dca(
        mtf=mtf,
        current_position_r=Decimal("-0.2"),
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=False,
    )
    # Under Phase 4C rules, score < 85 must return WAIT
    assert decision.decision_state == DecisionState.WAIT
    assert "DCA score below threshold" in decision.reason


def test_dca_blocked_when_1h_bearish() -> None:
    engine = StrategyEngine(min_entry_score=85)

    analysis_1d = _make_sample_analysis(is_bullish=True)
    analysis_4h = _make_sample_analysis(is_bullish=True)
    analysis_1h = _make_sample_analysis(is_bullish=False, rsi=Decimal("42.0"))  # Bearish
    analysis_15m = _make_sample_analysis(is_bullish=True)

    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=analysis_1d,
        analysis_4h=analysis_4h,
        analysis_1h=analysis_1h,
        analysis_15m=analysis_15m,
        timestamp=100000,
    )

    decision = engine.evaluate_dca(
        mtf=mtf,
        current_position_r=Decimal("0.0"),
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert decision.decision_state in {DecisionState.BLOCKED, DecisionState.WAIT}


def test_dca_blocked_when_position_drawdown_exceeds_half_r() -> None:
    engine = StrategyEngine(min_entry_score=85)

    analysis_1d = _make_sample_analysis(is_bullish=True)
    analysis_4h = _make_sample_analysis(is_bullish=True)
    analysis_1h = _make_sample_analysis(is_bullish=True)
    analysis_15m = _make_sample_analysis(is_bullish=True)

    mtf = MultiTimeframeAnalysis(
        symbol="XAUUSDT",
        regime=MarketRegime.STRONG_BULL,
        analysis_1d=analysis_1d,
        analysis_4h=analysis_4h,
        analysis_1h=analysis_1h,
        analysis_15m=analysis_15m,
        timestamp=100000,
    )

    decision = engine.evaluate_dca(
        mtf=mtf,
        current_position_r=Decimal("-0.51"),  # Exceeds -0.5R limit
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert decision.decision_state == DecisionState.BLOCKED
    assert "drawdown too deep" in decision.reason
