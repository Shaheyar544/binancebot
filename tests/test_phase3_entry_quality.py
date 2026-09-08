"""Unit tests covering Phase 3 entry quality improvements."""

from decimal import Decimal

from src.analysis.regime import RegimeClassifier
from src.domain.enums import MarketRegime, Timeframe
from src.domain.models import Candle
from src.strategy.entry_families import EntryFamily, TrendPullbackDetector
from src.strategy.scoring import StrategyScorer


def test_fix_3_1_reweighted_scoring_gradient_discrimination() -> None:
    """StrategyScorer produces full 100.0 on perfect conditions and discriminates gradients."""
    scorer = StrategyScorer()
    assert scorer.max_possible_score() == Decimal("100.0")

    # Perfect conditions: 10 + 15 + 15 + 15 + 15 + 10 + 10 + 10 = 100.0
    breakdown_perfect = scorer.calculate_gradient(
        htf_1d_bullish=True,
        htf_4h_bullish=True,
        htf_1h_bullish=True,
        setup_15m_bullish=True,
        close_15m=Decimal("2750.0"),
        ema_10=Decimal("2740.0"),
        ema_20=Decimal("2730.0"),
        ema_50=Decimal("2720.0"),
        ema_200=Decimal("2650.0"),
        rsi_1h=Decimal("60.0"),
        volume_ratio_15m=Decimal("1.6"),
        favorable_rr=True,
        reward_ratio=Decimal("3.5"),
    )
    assert breakdown_perfect.total_score == Decimal("100.0")
    assert breakdown_perfect.is_actionable(Decimal("85.0"))

    # Weak gradient conditions (RSI 42, volume 0.7, poor EMA, poor R:R) -> fails 85 threshold
    breakdown_weak = scorer.calculate_gradient(
        htf_1d_bullish=True,
        htf_4h_bullish=True,
        htf_1h_bullish=True,
        setup_15m_bullish=True,
        close_15m=Decimal("2700.0"),
        ema_10=Decimal("2705.0"),
        ema_20=Decimal("2690.0"),
        ema_50=Decimal("2710.0"),  # close <= ema_50 -> 0.0 pts
        ema_200=Decimal("2650.0"),
        rsi_1h=Decimal("38.0"),  # < 40 -> 0.0 pts
        volume_ratio_15m=Decimal("0.7"),  # < 0.8 -> 0.0 pts
        favorable_rr=False,
        reward_ratio=Decimal("0.5"),  # 0.0 pts
    )
    # Binary: 10 + 15 + 15 + 15 = 55.0. Gradients = 0. Total = 55.0
    assert breakdown_weak.total_score == Decimal("55.0")
    assert not breakdown_weak.is_actionable(Decimal("85.0"))


def test_fix_3_2_weighted_regime_classification() -> None:
    """RegimeClassifier.classify_weighted aggregates multi-timeframe regimes with 4H dominance."""
    classifier = RegimeClassifier()

    # Case 1: 4H=STRONG_BULL, 1H=BULL, 15M=BEARISH_RANGE
    # Composite is BULL (not dragged down to BEARISH_RANGE)
    reg_composite = classifier.classify_weighted(
        regime_4h=MarketRegime.STRONG_BULL,
        regime_1h=MarketRegime.BULL,
        regime_15m=MarketRegime.BEARISH_RANGE,
    )
    # Score: 3.0*0.5 + 2.0*0.3 + (-1.0)*0.2 = 1.5 + 0.6 - 0.2 = 1.9 -> BULL
    assert reg_composite == MarketRegime.BULL

    # Case 2: 4H=BEARISH_RANGE (veto) -> Composite is BEARISH_RANGE regardless of 15M STRONG_BULL
    reg_veto = classifier.classify_weighted(
        regime_4h=MarketRegime.BEARISH_RANGE,
        regime_1h=MarketRegime.BULL,
        regime_15m=MarketRegime.STRONG_BULL,
    )
    assert reg_veto == MarketRegime.BEARISH_RANGE

    # Case 3: All STRONG_BULL
    reg_all_bull = classifier.classify_weighted(
        regime_4h=MarketRegime.STRONG_BULL,
        regime_1h=MarketRegime.STRONG_BULL,
        regime_15m=MarketRegime.STRONG_BULL,
    )
    assert reg_all_bull == MarketRegime.STRONG_BULL


def test_fix_3_4_trend_pullback_tolerance() -> None:
    """TrendPullbackDetector accepts wicks that penetrate up to 0.2*ATR below EMA 50."""
    detector = TrendPullbackDetector()
    atr = Decimal("10.0")  # 0.2*ATR = 2.0
    ema_20 = Decimal("2720.0")
    ema_50 = Decimal("2700.0")  # lower zone = 2700.0, allowed lower = 2698.0

    # Candle dips to 2699.0 (1.0 below 2700, within 2.0 tolerance) and closes at 2705 (bullish)
    c_valid_wick = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2702.0"),
        high=Decimal("2710.0"),
        low=Decimal("2699.0"),
        close=Decimal("2705.0"),
        volume=Decimal("100.0"),
        close_time=1700000000000 + 900000 - 1,
        is_closed=True,
    )
    setup = detector.evaluate(c_valid_wick, ema_20=ema_20, ema_50=ema_50, atr=atr)
    assert setup is not None
    assert setup.family == EntryFamily.TREND_PULLBACK

    # Candle dips to 2695.0 (5.0 below 2700, exceeds 2.0 tolerance) -> rejected
    c_deep_wick = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2702.0"),
        high=Decimal("2710.0"),
        low=Decimal("2695.0"),
        close=Decimal("2705.0"),
        volume=Decimal("100.0"),
        close_time=1700000000000 + 900000 - 1,
        is_closed=True,
    )
    setup_deep = detector.evaluate(c_deep_wick, ema_20=ema_20, ema_50=ema_50, atr=atr)
    assert setup_deep is None
