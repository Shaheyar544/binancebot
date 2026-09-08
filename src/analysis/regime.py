"""Market regime classification based on multi-timeframe EMAs, structure, and volatility."""

from decimal import Decimal

from src.domain.enums import MarketRegime


class RegimeClassifier:
    """Classifies market conditions into deterministic regimes."""

    def __init__(self, volatility_expansion_multiplier: Decimal = Decimal("2.0")) -> None:
        self.volatility_expansion_multiplier = volatility_expansion_multiplier

    def classify(
        self,
        ema_10: Decimal,
        ema_20: Decimal,
        ema_50: Decimal,
        ema_200: Decimal,
        current_close: Decimal,
        atr: Decimal,
        avg_atr: Decimal,
        is_bullish_structure: bool,
    ) -> MarketRegime:
        """Determine regime based on moving averages, structure, and ATR."""
        # High volatility check first
        if avg_atr > Decimal("0") and atr >= avg_atr * self.volatility_expansion_multiplier:
            return MarketRegime.HIGH_VOLATILITY

        # Perfect full Bullish EMA alignment (10 > 20 > 50 > 200)
        is_full_bull_alignment = (
            current_close > ema_10 and ema_10 > ema_20 and ema_20 > ema_50 and ema_50 > ema_200
        )

        # Moderate Bullish EMA alignment (close > 20 > 50)
        is_moderate_bull = current_close > ema_20 and ema_20 > ema_50

        # Perfect full Bearish EMA alignment (10 < 20 < 50 < 200)
        is_full_bear_alignment = (
            current_close < ema_10 and ema_10 < ema_20 and ema_20 < ema_50 and ema_50 < ema_200
        )

        # Moderate Bearish EMA alignment (close < 20 < 50)
        is_moderate_bear = current_close < ema_20 and ema_20 < ema_50

        # 1. Strong Bull: Full EMA alignment + confirmed bullish structure
        if is_full_bull_alignment and is_bullish_structure:
            return MarketRegime.STRONG_BULL

        # 2. Bull: Moderate/Full EMA alignment + bullish structure
        if is_moderate_bull and is_bullish_structure:
            return MarketRegime.BULL

        # 3. Strong Bear: Full Bearish EMA alignment + bearish structure
        if is_full_bear_alignment and not is_bullish_structure:
            return MarketRegime.STRONG_BEAR

        # 4. Bear: Moderate/Full Bearish alignment + bearish structure
        if is_moderate_bear and not is_bullish_structure:
            return MarketRegime.BEAR

        # 5. Bullish Range: Price above EMA 50, but structure or EMA alignment is mixed/ranging
        if current_close > ema_50 and is_bullish_structure:
            return MarketRegime.BULLISH_RANGE

        # 6. Bearish Range: Price below EMA 50, but structure or EMA alignment is mixed/ranging
        if current_close < ema_50 and not is_bullish_structure:
            return MarketRegime.BEARISH_RANGE

        return MarketRegime.NEUTRAL

    def classify_weighted(
        self,
        regime_4h: MarketRegime,
        regime_1h: MarketRegime,
        regime_15m: MarketRegime,
    ) -> MarketRegime:
        """Composite regime using higher-timeframe dominance.

        4H has veto power: if 4H is BEAR/STRONG_BEAR/BEARISH_RANGE,
        the composite cannot be bullish.

        Weighting: 4H (50%), 1H (30%), 15M (20%)
        """
        if MarketRegime.EVENT_RISK in {regime_4h, regime_1h, regime_15m}:
            return MarketRegime.EVENT_RISK

        if regime_15m == MarketRegime.HIGH_VOLATILITY or regime_1h == MarketRegime.HIGH_VOLATILITY:
            return MarketRegime.HIGH_VOLATILITY

        # 4H Veto rule: if 4H is hostile, composite cannot be bullish
        if regime_4h in {MarketRegime.BEAR, MarketRegime.STRONG_BEAR, MarketRegime.BEARISH_RANGE}:
            return regime_4h

        # Score mapping
        score_map = {
            MarketRegime.STRONG_BULL: Decimal("3.0"),
            MarketRegime.BULL: Decimal("2.0"),
            MarketRegime.BULLISH_RANGE: Decimal("1.0"),
            MarketRegime.NEUTRAL: Decimal("0.0"),
            MarketRegime.BEARISH_RANGE: Decimal("-1.0"),
            MarketRegime.BEAR: Decimal("-2.0"),
            MarketRegime.STRONG_BEAR: Decimal("-3.0"),
            MarketRegime.HIGH_VOLATILITY: Decimal("0.0"),
            MarketRegime.EVENT_RISK: Decimal("0.0"),
        }

        s4 = score_map.get(regime_4h, Decimal("0.0"))
        s1 = score_map.get(regime_1h, Decimal("0.0"))
        sm = score_map.get(regime_15m, Decimal("0.0"))

        composite_score = (s4 * Decimal("0.50")) + (s1 * Decimal("0.30")) + (sm * Decimal("0.20"))

        if composite_score >= Decimal("2.5"):
            return MarketRegime.STRONG_BULL
        elif composite_score >= Decimal("1.5"):
            return MarketRegime.BULL
        elif composite_score >= Decimal("0.5"):
            return MarketRegime.BULLISH_RANGE
        elif composite_score <= Decimal("-2.5"):
            return MarketRegime.STRONG_BEAR
        elif composite_score <= Decimal("-1.5"):
            return MarketRegime.BEAR
        elif composite_score <= Decimal("-0.5"):
            return MarketRegime.BEARISH_RANGE
        else:
            return MarketRegime.NEUTRAL
