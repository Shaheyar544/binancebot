"""100-point multi-timeframe scoring engine."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ScoreBreakdown(BaseModel):
    """Immutable detailed breakdown of strategy alignment score."""

    model_config = ConfigDict(frozen=True)

    score_1d: Decimal = Field(..., ge=0, description="1D trend points (max 15)")
    score_4h: Decimal = Field(..., ge=0, description="4H structure points (max 20)")
    score_1h: Decimal = Field(..., ge=0, description="1H confirmation points (max 20)")
    score_15m: Decimal = Field(..., ge=0, description="15M setup points (max 20)")
    score_ema: Decimal = Field(..., ge=0, description="EMA alignment points (max 10)")
    score_momentum: Decimal = Field(..., ge=0, description="Momentum RSI/MACD points (max 5)")
    score_volume: Decimal = Field(..., ge=0, description="Volume confirmation points (max 5)")
    score_rr: Decimal = Field(..., ge=0, description="Risk-Reward quality points (max 5)")

    @property
    def total_score(self) -> Decimal:
        """Sum of all score components."""
        return (
            self.score_1d
            + self.score_4h
            + self.score_1h
            + self.score_15m
            + self.score_ema
            + self.score_momentum
            + self.score_volume
            + self.score_rr
        )

    def is_actionable(self, threshold: Decimal = Decimal("85.0")) -> bool:
        """Check if score meets or exceeds actionable threshold."""
        return self.total_score >= threshold


class StrategyScorer:
    """Calculates weighted multi-timeframe alignment score."""

    WEIGHT_1D = Decimal("15.0")
    WEIGHT_4H = Decimal("20.0")
    WEIGHT_1H = Decimal("20.0")
    WEIGHT_15M = Decimal("20.0")
    WEIGHT_EMA = Decimal("10.0")
    WEIGHT_MOMENTUM = Decimal("5.0")
    WEIGHT_VOLUME = Decimal("5.0")
    WEIGHT_RR = Decimal("5.0")

    def max_possible_score(self) -> Decimal:
        """Maximum possible score when all components pass (100.0)."""
        return (
            self.WEIGHT_1D
            + self.WEIGHT_4H
            + self.WEIGHT_1H
            + self.WEIGHT_15M
            + self.WEIGHT_EMA
            + self.WEIGHT_MOMENTUM
            + self.WEIGHT_VOLUME
            + self.WEIGHT_RR
        )

    def calculate(
        self,
        htf_1d_bullish: bool,
        htf_4h_bullish: bool,
        htf_1h_bullish: bool,
        setup_15m_bullish: bool,
        ema_aligned: bool,
        momentum_aligned: bool,
        volume_confirmed: bool,
        favorable_rr: bool,
    ) -> ScoreBreakdown:
        """Compute score breakdown based on technical alignment."""
        zero = Decimal("0.0")
        return ScoreBreakdown(
            score_1d=self.WEIGHT_1D if htf_1d_bullish else zero,
            score_4h=self.WEIGHT_4H if htf_4h_bullish else zero,
            score_1h=self.WEIGHT_1H if htf_1h_bullish else zero,
            score_15m=self.WEIGHT_15M if setup_15m_bullish else zero,
            score_ema=self.WEIGHT_EMA if ema_aligned else zero,
            score_momentum=self.WEIGHT_MOMENTUM if momentum_aligned else zero,
            score_volume=self.WEIGHT_VOLUME if volume_confirmed else zero,
            score_rr=self.WEIGHT_RR if favorable_rr else zero,
        )
