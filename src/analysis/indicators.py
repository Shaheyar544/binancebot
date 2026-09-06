"""Deterministic technical indicator calculations using Python Decimal."""

import math
from decimal import Decimal

from src.domain.models import Candle


def calculate_ema(prices: list[Decimal], period: int) -> Decimal:
    """Calculate Exponential Moving Average (EMA) for a price series."""
    if len(prices) < period:
        raise ValueError(
            f"Insufficient data points for EMA-{period}: got {len(prices)}, need at least {period}"
        )

    # Initial SMA of first `period` items
    sma = sum(prices[:period], Decimal("0")) / Decimal(str(period))
    multiplier = Decimal("2.0") / Decimal(str(period + 1))

    current_ema = sma
    for price in prices[period:]:
        current_ema = (price - current_ema) * multiplier + current_ema

    return current_ema


def calculate_rsi(prices: list[Decimal], period: int = 14) -> Decimal:
    """Calculate Relative Strength Index (RSI) using Wilder's smoothed method."""
    if len(prices) < period + 1:
        raise ValueError(
            f"Insufficient data points for RSI-{period}: "
            f"got {len(prices)}, need at least {period + 1}"
        )

    gains: list[Decimal] = []
    losses: list[Decimal] = []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff > Decimal("0"):
            gains.append(diff)
            losses.append(Decimal("0"))
        else:
            gains.append(Decimal("0"))
            losses.append(abs(diff))

    avg_gain = sum(gains[:period], Decimal("0")) / Decimal(str(period))
    avg_loss = sum(losses[:period], Decimal("0")) / Decimal(str(period))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * Decimal(str(period - 1)) + gains[i]) / Decimal(str(period))
        avg_loss = (avg_loss * Decimal(str(period - 1)) + losses[i]) / Decimal(str(period))

    if avg_loss == Decimal("0"):
        return Decimal("100.0")
    if avg_gain == Decimal("0"):
        return Decimal("0.0")

    rs = avg_gain / avg_loss
    rsi = Decimal("100.0") - (Decimal("100.0") / (Decimal("1.0") + rs))
    return round(rsi, 2)


def calculate_macd(
    prices: list[Decimal], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate MACD line, signal line, and histogram."""
    if len(prices) < slow + signal:
        raise ValueError(
            f"Insufficient data points for MACD: got {len(prices)}, need at least {slow + signal}"
        )

    # Compute fast and slow EMA series
    macd_series: list[Decimal] = []
    for i in range(slow, len(prices) + 1):
        subset = prices[:i]
        fast_ema = calculate_ema(subset, fast)
        slow_ema = calculate_ema(subset, slow)
        macd_series.append(fast_ema - slow_ema)

    signal_line = calculate_ema(macd_series, signal)
    macd_line = macd_series[-1]
    hist = macd_line - signal_line

    return (round(macd_line, 4), round(signal_line, 4), round(hist, 4))


def calculate_atr(candles: list[Candle], period: int = 14) -> Decimal:
    """Calculate Average True Range (ATR) for volatility measurement."""
    if len(candles) < period:
        raise ValueError(
            f"Insufficient candles for ATR-{period}: got {len(candles)}, need at least {period}"
        )

    tr_list: list[Decimal] = []
    for i in range(len(candles)):
        c = candles[i]
        if i == 0:
            tr = c.high - c.low
        else:
            prev_close = candles[i - 1].close
            tr = max(
                c.high - c.low,
                abs(c.high - prev_close),
                abs(c.low - prev_close),
            )
        tr_list.append(tr)

    # Simple smoothed average over the period
    recent_tr = tr_list[-period:]
    atr = sum(recent_tr, Decimal("0")) / Decimal(str(period))
    return round(atr, 2)


def calculate_bollinger_bands(
    prices: list[Decimal], period: int = 20, num_std: float = 2.0
) -> tuple[Decimal, Decimal, Decimal]:
    """Calculate Bollinger Bands (upper, middle, lower)."""
    if len(prices) < period:
        raise ValueError(
            f"Insufficient data points for Bollinger Bands: "
            f"got {len(prices)}, need at least {period}"
        )

    subset = prices[-period:]
    middle = sum(subset, Decimal("0")) / Decimal(str(period))

    # Variance
    variance = sum(((p - middle) ** 2 for p in subset), Decimal("0")) / Decimal(str(period))
    std_dev = Decimal(str(round(math.sqrt(float(variance)), 4)))

    multiplier = Decimal(str(num_std))
    upper = middle + (std_dev * multiplier)
    lower = middle - (std_dev * multiplier)

    return (round(upper, 2), round(middle, 2), round(lower, 2))


def calculate_volume_ratio(volumes: list[Decimal], period: int = 20) -> Decimal:
    """Calculate volume surge ratio comparing the latest volume to moving average."""
    if len(volumes) < period:
        return Decimal("1.0")

    subset = volumes[-period:]
    avg_vol = sum(subset, Decimal("0")) / Decimal(str(period))
    if avg_vol == Decimal("0"):
        return Decimal("1.0")

    ratio = volumes[-1] / avg_vol
    return round(ratio, 2)
