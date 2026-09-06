"""Tests for market regime detection and classification."""

from decimal import Decimal

from src.analysis.regime import RegimeClassifier
from src.domain.enums import MarketRegime


def test_classify_strong_bull_regime() -> None:
    """Stacked bullish EMAs (10 > 20 > 50 > 200) classify as STRONG_BULL."""
    classifier = RegimeClassifier()
    regime = classifier.classify(
        ema_10=Decimal("2750.0"),
        ema_20=Decimal("2730.0"),
        ema_50=Decimal("2700.0"),
        ema_200=Decimal("2650.0"),
        current_close=Decimal("2760.0"),
        atr=Decimal("15.0"),
        avg_atr=Decimal("15.0"),
        is_bullish_structure=True,
    )
    assert regime == MarketRegime.STRONG_BULL


def test_classify_bear_regime() -> None:
    """Stacked bearish EMAs (10 < 20 < 50 < 200) classify as BEAR or STRONG_BEAR."""
    classifier = RegimeClassifier()
    regime = classifier.classify(
        ema_10=Decimal("2650.0"),
        ema_20=Decimal("2680.0"),
        ema_50=Decimal("2700.0"),
        ema_200=Decimal("2730.0"),
        current_close=Decimal("2640.0"),
        atr=Decimal("15.0"),
        avg_atr=Decimal("15.0"),
        is_bullish_structure=False,
    )
    assert regime in {MarketRegime.BEAR, MarketRegime.STRONG_BEAR}


def test_classify_high_volatility_regime() -> None:
    """Abnormally high ATR relative to average triggers HIGH_VOLATILITY."""
    classifier = RegimeClassifier()
    regime = classifier.classify(
        ema_10=Decimal("2750.0"),
        ema_20=Decimal("2730.0"),
        ema_50=Decimal("2700.0"),
        ema_200=Decimal("2650.0"),
        current_close=Decimal("2760.0"),
        atr=Decimal("45.0"),  # 3x normal volatility
        avg_atr=Decimal("15.0"),
        is_bullish_structure=True,
    )
    assert regime == MarketRegime.HIGH_VOLATILITY


def test_classify_bullish_range_and_neutral_regimes() -> None:
    """Test classification of BULLISH_RANGE and NEUTRAL regimes."""
    classifier = RegimeClassifier()
    # Above EMA 50 with bullish structure but mixed short-term EMAs
    range_regime = classifier.classify(
        ema_10=Decimal("2710.0"),
        ema_20=Decimal("2715.0"),
        ema_50=Decimal("2700.0"),
        ema_200=Decimal("2680.0"),
        current_close=Decimal("2712.0"),
        atr=Decimal("15.0"),
        avg_atr=Decimal("15.0"),
        is_bullish_structure=True,
    )
    assert range_regime == MarketRegime.BULLISH_RANGE

    # Neutral regime: choppy price and conflicting structure
    neutral_regime = classifier.classify(
        ema_10=Decimal("2700.0"),
        ema_20=Decimal("2710.0"),
        ema_50=Decimal("2705.0"),
        ema_200=Decimal("2690.0"),
        current_close=Decimal("2708.0"),
        atr=Decimal("15.0"),
        avg_atr=Decimal("15.0"),
        is_bullish_structure=False,
    )
    assert neutral_regime == MarketRegime.NEUTRAL
