"""Tests for the 100-point multi-timeframe strategy scoring model."""

from decimal import Decimal

from src.strategy.scoring import ScoreBreakdown, StrategyScorer


def test_scoring_weights_sum_to_100() -> None:
    """Configurable scoring components must sum to 100 points maximum."""
    scorer = StrategyScorer()
    max_score = scorer.max_possible_score()
    assert max_score == Decimal("100.0")


def test_perfect_score_evaluation() -> None:
    """All criteria met generates 100/100 points."""
    scorer = StrategyScorer()
    breakdown: ScoreBreakdown = scorer.calculate(
        htf_1d_bullish=True,  # 15 pts
        htf_4h_bullish=True,  # 20 pts
        htf_1h_bullish=True,  # 20 pts
        setup_15m_bullish=True,  # 20 pts
        ema_aligned=True,  # 10 pts
        momentum_aligned=True,  # 5 pts
        volume_confirmed=True,  # 5 pts
        favorable_rr=True,  # 5 pts
    )
    assert breakdown.total_score == Decimal("100.0")
    assert breakdown.is_actionable(threshold=Decimal("85.0")) is True


def test_partial_score_below_threshold() -> None:
    """Score below 85 points fails actionable threshold."""
    scorer = StrategyScorer()
    breakdown = scorer.calculate(
        htf_1d_bullish=True,  # 15
        htf_4h_bullish=True,  # 20
        htf_1h_bullish=False,  # 0
        setup_15m_bullish=True,  # 20
        ema_aligned=True,  # 10
        momentum_aligned=False,  # 0
        volume_confirmed=True,  # 5
        favorable_rr=True,  # 5
    )
    # Total = 15 + 20 + 0 + 20 + 10 + 0 + 5 + 5 = 75
    assert breakdown.total_score == Decimal("75.0")
    assert breakdown.is_actionable(threshold=Decimal("85.0")) is False


def test_gradient_scoring_evaluation() -> None:
    """Gradient scoring accurately rewards partial technical alignment."""
    scorer = StrategyScorer()
    breakdown = scorer.calculate_gradient(
        htf_1d_bullish=True,  # 10.0
        htf_4h_bullish=True,  # 15.0
        htf_1h_bullish=True,  # 15.0
        setup_15m_bullish=True,  # 15.0
        close_15m=Decimal("2750.0"),
        ema_10=Decimal("2740.0"),
        ema_20=Decimal("2730.0"),
        ema_50=Decimal("2720.0"),
        ema_200=Decimal("2760.0"),  # Close > 10 > 20 > 50 (strong alignment -> 12.0 pts)
        rsi_1h=Decimal("58.0"),  # Optimal bull momentum -> 10.0 pts
        volume_ratio_15m=Decimal("1.3"),  # Volume 1.2-1.5 -> 9.0 pts
        favorable_rr=True,  # 10.0 pts
    )
    # Total = 10 + 15 + 15 + 15 + 12.0 + 10.0 + 9.0 + 10.0 = 96.0
    assert breakdown.total_score == Decimal("96.0")
    assert breakdown.is_actionable(threshold=Decimal("85.0")) is True
