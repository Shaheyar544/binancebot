"""Macro advisory layer producing structured evidence assessments without execution rights."""

import time
import uuid
from decimal import Decimal

from src.macro.models import EventClassification, MacroAssessment


class MacroAdvisor:
    """Produces advisory macro intelligence with strict evidence classification.

    Has ZERO order placement or live execution capabilities.
    """

    def assess(
        self,
        classification: EventClassification,
        gold_catalyst_bias: str,
        confidence_score: Decimal,
        summary: str,
        reasoning: str,
        source: str,
    ) -> MacroAssessment:
        """Create structured, immutable macro evaluation record."""
        return MacroAssessment(
            assessment_id=f"MACRO_{uuid.uuid4().hex[:8]}",
            timestamp_ms=int(time.time() * 1000),
            classification=classification,
            gold_catalyst_bias=gold_catalyst_bias,
            confidence_score=confidence_score,
            summary=summary,
            reasoning=reasoning,
            source=source,
        )
