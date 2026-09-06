"""Adaptive long-only strategy evaluation engine."""

import uuid
from decimal import Decimal

from src.analysis.models import MultiTimeframeAnalysis
from src.domain.enums import DecisionState
from src.domain.models import DecisionSnapshot
from src.market_data.enums import MarketDataHealth
from src.strategy.scoring import StrategyScorer


class StrategyEngine:
    """Evaluates multi-timeframe analysis and produces candidate trade decisions."""

    def __init__(self, min_entry_score: int | Decimal = 85) -> None:
        self.min_entry_score = Decimal(str(min_entry_score))
        self.scorer = StrategyScorer()

    def evaluate(
        self,
        mtf: MultiTimeframeAnalysis,
        data_health: MarketDataHealth,
        has_setup: bool,
        favorable_rr: bool,
    ) -> DecisionSnapshot:
        """Evaluate market conditions against rules and generate a decision snapshot."""
        # Safety gate 1: Unsafe market data
        if data_health != MarketDataHealth.HEALTHY:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.DATA_UNSAFE,
                regime=mtf.regime,
                reason=f"Market data health is unsafe ({data_health.value})",
                timestamp=mtf.timestamp,
            )

        # Safety gate 2: Higher timeframe structure must not be bearish
        if not mtf.analysis_1d.is_bullish or not mtf.analysis_4h.is_bullish:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BLOCKED,
                regime=mtf.regime,
                reason="Higher-timeframe structure is bearish; long entries prohibited",
                timestamp=mtf.timestamp,
            )

        # Calculate multi-timeframe alignment score
        breakdown = self.scorer.calculate(
            htf_1d_bullish=mtf.analysis_1d.is_bullish,
            htf_4h_bullish=mtf.analysis_4h.is_bullish,
            htf_1h_bullish=mtf.analysis_1h.is_bullish,
            setup_15m_bullish=has_setup,
            ema_aligned=(
                mtf.analysis_15m.current_close > mtf.analysis_15m.ema_10
                and mtf.analysis_15m.ema_10 > mtf.analysis_15m.ema_20
                and mtf.analysis_15m.ema_20 > mtf.analysis_15m.ema_50
            ),
            momentum_aligned=mtf.analysis_1h.rsi > Decimal("50.0"),
            volume_confirmed=mtf.analysis_15m.volume_ratio >= Decimal("1.2"),
            favorable_rr=favorable_rr,
        )

        total_score = breakdown.total_score

        if breakdown.is_actionable(self.min_entry_score) and has_setup:
            return DecisionSnapshot(
                decision_id=str(uuid.uuid4()),
                symbol=mtf.symbol,
                decision_state=DecisionState.BUY,
                regime=mtf.regime,
                reason=f"High conviction bullish setup aligned (score={total_score})",
                timestamp=mtf.timestamp,
            )

        return DecisionSnapshot(
            decision_id=str(uuid.uuid4()),
            symbol=mtf.symbol,
            decision_state=DecisionState.WAIT,
            regime=mtf.regime,
            reason=f"Score below entry threshold ({total_score} < {self.min_entry_score})",
            timestamp=mtf.timestamp,
        )
