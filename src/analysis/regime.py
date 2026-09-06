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

        # Bullish EMA alignment
        is_bull_alignment = (
            current_close > ema_10 and ema_10 > ema_20 and ema_20 > ema_50 and ema_50 > ema_200
        )

        # Bearish EMA alignment
        is_bear_alignment = (
            current_close < ema_10 and ema_10 < ema_20 and ema_20 < ema_50 and ema_50 < ema_200
        )

        if is_bull_alignment and is_bullish_structure:
            return MarketRegime.STRONG_BULL

        if is_bear_alignment and not is_bullish_structure:
            return MarketRegime.STRONG_BEAR

        if is_bear_alignment or (current_close < ema_50 and not is_bullish_structure):
            return MarketRegime.BEAR

        if is_bull_alignment or (current_close > ema_50 and is_bullish_structure):
            return MarketRegime.BULLISH_RANGE

        return MarketRegime.NEUTRAL
