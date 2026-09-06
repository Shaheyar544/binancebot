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
