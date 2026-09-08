"""Unit tests covering Phase 1 fixes."""

from decimal import Decimal
from unittest.mock import MagicMock

from src.analysis.regime import RegimeClassifier
from src.domain.enums import DecisionState, MarketRegime, Timeframe
from src.domain.models import Candle
from src.market_data.enums import MarketDataHealth
from src.strategy.engine import StrategyEngine
from src.strategy.entry_families import EntryFamily, EntryOrchestrator, SupportReclaimDetector


def test_fix_1_1_high_volatility_regime_classification() -> None:
    """Regime classifier correctly detects HIGH_VOLATILITY when ATR is 2x avg_atr."""
    classifier = RegimeClassifier(volatility_expansion_multiplier=Decimal("2.0"))

    # Case 1: ATR = 30.0, avg_atr = 10.0 -> 30 >= 20 -> HIGH_VOLATILITY
    regime = classifier.classify(
        ema_10=Decimal("2710"),
        ema_20=Decimal("2705"),
        ema_50=Decimal("2700"),
        ema_200=Decimal("2650"),
        current_close=Decimal("2720"),
        atr=Decimal("30.0"),
        avg_atr=Decimal("10.0"),
        is_bullish_structure=True,
    )
    assert regime == MarketRegime.HIGH_VOLATILITY

    # Case 2: ATR = 15.0, avg_atr = 10.0 -> 15 < 20 -> STRONG_BULL
    regime_normal = classifier.classify(
        ema_10=Decimal("2710"),
        ema_20=Decimal("2705"),
        ema_50=Decimal("2700"),
        ema_200=Decimal("2650"),
        current_close=Decimal("2720"),
        atr=Decimal("15.0"),
        avg_atr=Decimal("10.0"),
        is_bullish_structure=True,
    )
    assert regime_normal == MarketRegime.STRONG_BULL

    # Case 3: ATR = 10.0, avg_atr = 10.0 (equal) -> Not HIGH_VOLATILITY
    regime_equal = classifier.classify(
        ema_10=Decimal("2710"),
        ema_20=Decimal("2705"),
        ema_50=Decimal("2700"),
        ema_200=Decimal("2650"),
        current_close=Decimal("2720"),
        atr=Decimal("10.0"),
        avg_atr=Decimal("10.0"),
        is_bullish_structure=True,
    )
    assert regime_equal == MarketRegime.STRONG_BULL


def test_fix_1_2_bearish_range_blocked() -> None:
    """StrategyEngine blocks BEARISH_RANGE regime from taking long entries."""
    engine = StrategyEngine(min_entry_score=85)
    mock_mtf = MagicMock()
    mock_mtf.symbol = "XAUUSDT"
    mock_mtf.timestamp = 1700000000000
    mock_mtf.analysis_1d.is_bullish = True
    mock_mtf.analysis_4h.is_bullish = True
    mock_mtf.regime = MarketRegime.BEARISH_RANGE

    decision = engine.evaluate(
        mtf=mock_mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert decision.decision_state == DecisionState.BLOCKED
    assert "hostile to long entries" in decision.reason


def test_fix_1_3_bullish_range_elevated_threshold() -> None:
    """BULLISH_RANGE requires score >= 90.0."""
    engine = StrategyEngine(min_entry_score=85)
    mock_mtf = MagicMock()
    mock_mtf.symbol = "XAUUSDT"
    mock_mtf.timestamp = 1700000000000
    mock_mtf.analysis_1d.is_bullish = True
    mock_mtf.analysis_4h.is_bullish = True
    mock_mtf.analysis_1h.is_bullish = True
    mock_mtf.analysis_15m.current_close = Decimal("2700.0")
    # Not full EMA alignment: ema_10 < ema_20 -> ema_aligned = False (-10 pts)
    mock_mtf.analysis_15m.ema_10 = Decimal("2685.0")
    mock_mtf.analysis_15m.ema_20 = Decimal("2690.0")
    mock_mtf.analysis_15m.ema_50 = Decimal("2680.0")
    mock_mtf.analysis_15m.ema_200 = Decimal("2650.0")
    mock_mtf.analysis_1h.rsi = Decimal("45.0")
    mock_mtf.analysis_15m.volume_ratio = Decimal("1.2")
    mock_mtf.regime = MarketRegime.BULLISH_RANGE

    # Legacy calculate produces score 85.0 when all aligned
    decision = engine.evaluate(
        mtf=mock_mtf,
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
        use_gradient_scoring=False,
    )
    # Score is below 90.0 requirement for BULLISH_RANGE -> WAIT
    assert decision.decision_state == DecisionState.WAIT
    assert "< 90.0" in decision.reason


def test_fix_1_4_support_reclaim_disabled_in_orchestrator() -> None:
    """EntryOrchestrator skips SUPPORT_RECLAIM but SupportReclaimDetector class still works."""
    orchestrator = EntryOrchestrator()
    detector = SupportReclaimDetector()

    candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2700.0"),
        high=Decimal("2705.0"),
        low=Decimal("2685.0"),
        close=Decimal("2698.0"),
        volume=Decimal("100.0"),
        close_time=1700000000000 + 900000 - 1,
        is_closed=True,
    )

    # Direct detector still detects the sweep & reclaim
    direct_setup = detector.evaluate(candle, support_level=Decimal("2690.0"), atr=Decimal("10.0"))
    assert direct_setup is not None
    assert direct_setup.family == EntryFamily.SUPPORT_RECLAIM

    # Orchestrator does NOT return SUPPORT_RECLAIM even when support_level is provided
    orch_setup = orchestrator.evaluate_setups(
        candles_15m=[candle],
        ema_20=Decimal("2650.0"),
        ema_50=Decimal("2640.0"),
        support_level=Decimal("2690.0"),
        resistance_level=None,
        atr=Decimal("10.0"),
    )
    assert orch_setup is None
