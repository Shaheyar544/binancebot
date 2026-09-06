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
    """Calculates weighted multi-timeframe alignment score with gradient precision."""

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

    @staticmethod
    def calculate_momentum_score(rsi_1h: Decimal) -> Decimal:
        """Gradient momentum score based on 1H RSI:

        < 40: 0.0
        40 - 50: 1.5
        50 - 55: 3.0
        55 - 65: 5.0 (optimal bull momentum)
        65 - 75: 4.0
        > 75: 2.5 (overbought warning)
        """
        if rsi_1h < Decimal("40.0"):
            return Decimal("0.0")
        elif rsi_1h < Decimal("50.0"):
            return Decimal("1.5")
        elif rsi_1h < Decimal("55.0"):
            return Decimal("3.0")
        elif rsi_1h <= Decimal("65.0"):
            return Decimal("5.0")
        elif rsi_1h <= Decimal("75.0"):
            return Decimal("4.0")
        else:
            return Decimal("2.5")

    @staticmethod
    def calculate_volume_score(volume_ratio: Decimal) -> Decimal:
        """Gradient volume confirmation score:

        < 0.8: 0.0
        0.8 - 1.0: 1.5
        1.0 - 1.2: 3.0
        1.2 - 1.5: 4.5
        >= 1.5: 5.0 (strong institutional confirmation)
        """
        if volume_ratio < Decimal("0.8"):
            return Decimal("0.0")
        elif volume_ratio < Decimal("1.0"):
            return Decimal("1.5")
        elif volume_ratio < Decimal("1.2"):
            return Decimal("3.0")
        elif volume_ratio < Decimal("1.5"):
            return Decimal("4.5")
        else:
            return Decimal("5.0")

    @staticmethod
    def calculate_ema_score(
        close: Decimal,
        ema_10: Decimal,
        ema_20: Decimal,
        ema_50: Decimal,
        ema_200: Decimal,
    ) -> Decimal:
        """Gradient EMA alignment score:

        Full alignment (close > 10 > 20 > 50 > 200): 10.0
        Strong alignment (close > 10 > 20 > 50): 8.0
        Moderate alignment (close > 20 > 50): 5.0
        Above long term (close > 50): 3.0
        Below long term (close <= 50): 0.0
        """
        if close > ema_10 > ema_20 > ema_50 > ema_200:
            return Decimal("10.0")
        elif close > ema_10 > ema_20 > ema_50:
            return Decimal("8.0")
        elif close > ema_20 > ema_50:
            return Decimal("5.0")
        elif close > ema_50:
            return Decimal("3.0")
        else:
            return Decimal("0.0")

    def calculate_gradient(
        self,
        htf_1d_bullish: bool,
        htf_4h_bullish: bool,
        htf_1h_bullish: bool,
        setup_15m_bullish: bool,
        close_15m: Decimal,
        ema_10: Decimal,
        ema_20: Decimal,
        ema_50: Decimal,
        ema_200: Decimal,
        rsi_1h: Decimal,
        volume_ratio_15m: Decimal,
        favorable_rr: bool,
    ) -> ScoreBreakdown:
        """Calculate continuous gradient score breakdown."""
        zero = Decimal("0.0")
        score_1d = self.WEIGHT_1D if htf_1d_bullish else zero
        score_4h = self.WEIGHT_4H if htf_4h_bullish else zero
        score_1h = self.WEIGHT_1H if htf_1h_bullish else zero
        score_15m = self.WEIGHT_15M if setup_15m_bullish else zero
        score_ema = self.calculate_ema_score(close_15m, ema_10, ema_20, ema_50, ema_200)
        score_momentum = self.calculate_momentum_score(rsi_1h)
        score_volume = self.calculate_volume_score(volume_ratio_15m)
        score_rr = self.WEIGHT_RR if favorable_rr else zero

        return ScoreBreakdown(
            score_1d=score_1d,
            score_4h=score_4h,
            score_1h=score_1h,
            score_15m=score_15m,
            score_ema=score_ema,
            score_momentum=score_momentum,
            score_volume=score_volume,
            score_rr=score_rr,
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
        """Compute score breakdown based on technical alignment (backward compatible)."""
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
