"""Tests for deterministic technical indicator calculations using Decimal precision."""

from decimal import Decimal

import pytest

from src.analysis.indicators import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_volume_ratio,
)
from src.domain.enums import Timeframe
from src.domain.models import Candle


def make_candle(open_p: str, high_p: str, low_p: str, close_p: str, vol: str = "100.0") -> Candle:
    return Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal(open_p),
        high=Decimal(high_p),
        low=Decimal(low_p),
        close=Decimal(close_p),
        volume=Decimal(vol),
        close_time=1700000899999,
        is_closed=True,
    )


def test_calculate_ema() -> None:
    """EMA calculation produces correct weighted moving average."""
    # Exponential / accelerating price series ensures recent prices are weighted higher
    prices = [Decimal(str(x)) for x in [10, 10, 10, 10, 10, 12, 14, 16, 20, 25]]
    ema = calculate_ema(prices, period=5)
    assert isinstance(ema, Decimal)
    sma = sum(prices[-5:], Decimal("0")) / Decimal("5")
    assert ema > sma


def test_calculate_ema_insufficient_data() -> None:
    """EMA raises ValueError when data points are fewer than period."""
    with pytest.raises(ValueError, match="Insufficient data points"):
        calculate_ema([Decimal("100.0")], period=5)


def test_calculate_rsi_rising_prices() -> None:
    """RSI for consistently rising prices must be high (>70)."""
    prices = [Decimal(str(100 + i * 2)) for i in range(20)]
    rsi = calculate_rsi(prices, period=14)
    assert isinstance(rsi, Decimal)
    assert rsi > Decimal("70.0")


def test_calculate_rsi_falling_prices() -> None:
    """RSI for consistently falling prices must be low (<30)."""
    prices = [Decimal(str(200 - i * 2)) for i in range(20)]
    rsi = calculate_rsi(prices, period=14)
    assert isinstance(rsi, Decimal)
    assert rsi < Decimal("30.0")


def test_calculate_macd() -> None:
    """MACD calculates macd_line, signal_line, and histogram."""
    prices = [Decimal(str(100 + i)) for i in range(40)]
    macd_line, signal_line, hist = calculate_macd(prices)
    assert isinstance(macd_line, Decimal)
    assert isinstance(signal_line, Decimal)
    assert isinstance(hist, Decimal)
    # In uptrend, MACD line is above 0
    assert macd_line > Decimal("0")


def test_calculate_atr() -> None:
    """ATR measures true range volatility over specified period."""
    candles = [make_candle("2700.0", "2710.0", "2690.0", "2705.0") for _ in range(20)]
    atr = calculate_atr(candles, period=14)
    assert isinstance(atr, Decimal)
    assert atr == Decimal("20.00")  # (2710 - 2690) = 20 on all candles


def test_calculate_bollinger_bands() -> None:
    """Bollinger Bands returns upper, middle, and lower bands."""
    prices = [Decimal("2700.00") for _ in range(20)]
    upper, middle, lower = calculate_bollinger_bands(prices, period=20, num_std=2.0)
    assert middle == Decimal("2700.00")
    # For zero variance, upper == middle == lower
    assert upper == middle == lower


def test_calculate_volume_ratio() -> None:
    """Volume ratio compares latest volume to moving average volume."""
    volumes = [Decimal("100.0") for _ in range(19)] + [Decimal("200.0")]
    ratio = calculate_volume_ratio(volumes, period=20)
    assert isinstance(ratio, Decimal)
    # Latest volume is 200, average is ~105, ratio ~1.9
    assert ratio > Decimal("1.8")


def test_decimal_sqrt() -> None:
    """Newton-Raphson square root accurately calculates roots with pure Decimal."""
    from src.analysis.indicators import _decimal_sqrt

    assert _decimal_sqrt(Decimal("0")) == Decimal("0")
    assert round(_decimal_sqrt(Decimal("4")), 4) == Decimal("2.0000")
    assert round(_decimal_sqrt(Decimal("2")), 4) == Decimal("1.4142")

    with pytest.raises(ValueError, match="Cannot calculate square root of negative number"):
        _decimal_sqrt(Decimal("-1"))


def test_timeframe_analyzer_analysis_pipeline() -> None:
    """TimeframeAnalyzer derives full TimeframeAnalysis and MultiTimeframeAnalysis correctly."""
    from src.analysis.models import TimeframeAnalyzer

    candles = [
        make_candle(str(2700 + i), str(2705 + i), str(2695 + i), str(2702 + i)) for i in range(25)
    ]
    tf_analysis = TimeframeAnalyzer.analyze_timeframe(candles, Timeframe.M15)
    assert tf_analysis.timeframe == Timeframe.M15
    assert tf_analysis.is_bullish is True
    assert tf_analysis.current_close == Decimal("2726")

    # Multi timeframe aggregation
    mtf = TimeframeAnalyzer.build_multi_timeframe_analysis(
        symbol="XAUUSDT",
        candles_1d=candles,
        candles_4h=candles,
        candles_1h=candles,
        candles_15m=candles,
    )
    assert mtf.symbol == "XAUUSDT"
    assert mtf.analysis_1d.is_bullish is True
    assert mtf.analysis_15m.current_close == Decimal("2726")
