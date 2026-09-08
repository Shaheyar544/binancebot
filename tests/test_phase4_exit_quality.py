"""Unit tests covering Phase 4 exit quality improvements."""

from decimal import Decimal
from unittest.mock import MagicMock

from src.domain.enums import DecisionState, MarketRegime
from src.market_data.enums import MarketDataHealth
from src.strategy.engine import ExitManager, StrategyEngine


def test_fix_4_1_dynamic_atr_breakeven_buffer() -> None:
    """update_breakeven_stop uses 0.3*ATR dynamic buffer when ATR is available."""
    from src.backtest.engine import BacktestEngine
    from src.backtest.models import BacktestConfig
    from src.config.settings import UserRiskConfig
    from src.domain.enums import Timeframe
    from src.domain.models import Candle

    cfg = BacktestConfig(
        user_risk_config=UserRiskConfig(
            allocated_funds=Decimal("1000"),
            leverage=Decimal("2"),
            max_acceptable_liquidation_price=Decimal("2000"),
        )
    )
    exit_mgr = ExitManager(
        enable_breakeven=True,
        breakeven_r_multiple=Decimal("1.0"),
        breakeven_buffer=Decimal("0.50"),  # default buffer trigger for dynamic ATR
    )
    engine = BacktestEngine(config=cfg, exit_manager=exit_mgr)

    dummy_candle = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2700.0"),
        high=Decimal("2720.0"),
        low=Decimal("2690.0"),
        close=Decimal("2715.0"),
        volume=Decimal("100.0"),
        close_time=1700000000000 + 900000 - 1,
        is_closed=True,
    )

    # Entry = 2700, Stop = 2690 (Initial R = 10), Highest = 2712 (>= 2710 -> trigger)
    # ATR = 20.0 -> Dynamic buffer = 0.3 * 20.0 = 6.0
    new_stop = engine.update_breakeven_stop(
        candle=dummy_candle,
        entry_price=Decimal("2700.0"),
        current_stop=Decimal("2690.0"),
        initial_r=Decimal("10.0"),
        highest_price=Decimal("2712.0"),
        current_atr=Decimal("20.0"),
    )
    # Stop ratchets to entry (2700) + buffer (6.0) = 2706.0
    assert new_stop == Decimal("2706.0")


def test_fix_4_3_evaluate_dca_high_conviction_qualification() -> None:
    """evaluate_dca permits ADD decisions on high conviction pullbacks with full 1H alignment
    and score >= 85.
    """
    engine = StrategyEngine(min_entry_score=85)

    mock_mtf = MagicMock()
    mock_mtf.symbol = "XAUUSDT"
    mock_mtf.timestamp = 1700000000000
    mock_mtf.analysis_1d.is_bullish = True
    mock_mtf.analysis_4h.is_bullish = True
    mock_mtf.analysis_1h.is_bullish = True
    mock_mtf.analysis_1h.rsi = Decimal("58.0")
    mock_mtf.analysis_15m.current_close = Decimal("2710.0")
    mock_mtf.analysis_15m.ema_10 = Decimal("2708.0")
    mock_mtf.analysis_15m.ema_20 = Decimal("2705.0")
    mock_mtf.analysis_15m.ema_50 = Decimal("2700.0")
    mock_mtf.analysis_15m.ema_200 = Decimal("2650.0")
    mock_mtf.analysis_15m.volume_ratio = Decimal("1.3")
    mock_mtf.regime = MarketRegime.STRONG_BULL

    # Shallow drawdown: -0.2R
    dca_dec = engine.evaluate_dca(
        mtf=mock_mtf,
        current_position_r=Decimal("-0.2"),
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert dca_dec.decision_state == DecisionState.ADD
    assert "DCA qualification approved" in dca_dec.reason

    # Deep drawdown: -0.8R -> BLOCKED
    dca_deep = engine.evaluate_dca(
        mtf=mock_mtf,
        current_position_r=Decimal("-0.8"),
        data_health=MarketDataHealth.HEALTHY,
        has_setup=True,
        favorable_rr=True,
    )
    assert dca_deep.decision_state == DecisionState.BLOCKED
    assert "too deep" in dca_deep.reason
