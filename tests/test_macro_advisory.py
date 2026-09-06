"""Tests for MacroAdvisor: evidence categorization and non-execution boundary."""

from decimal import Decimal

from src.macro.advisory import MacroAdvisor
from src.macro.models import EventClassification


def test_macro_advisor_evidence_classification() -> None:
    """Advisor strictly assigns evidence categories:
    FACT, EXPECTATION, ANALYSIS, AI_INTERPRETATION.
    """
    advisor = MacroAdvisor()

    assessment = advisor.assess(
        classification=EventClassification.AI_INTERPRETATION,
        gold_catalyst_bias="BULLISH",
        confidence_score=Decimal("0.85"),
        summary="Dovish Fed rhetoric increases gold safe-haven appeal",
        reasoning="Market pricing in 50bp rate cut at upcoming meeting",
        source="Federal Reserve FOMC Minutes & Yield Analysis",
    )

    assert assessment.classification == EventClassification.AI_INTERPRETATION
    assert assessment.gold_catalyst_bias == "BULLISH"
    assert assessment.confidence_score == Decimal("0.85")
    assert not hasattr(advisor, "submit_order")
    assert not hasattr(advisor, "place_order")
