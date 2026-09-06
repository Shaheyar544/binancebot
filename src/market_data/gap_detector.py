"""Gap detector for detecting sequence discontinuities in completed candle streams."""

import time

from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.market_data.enums import MarketDataHealth
from src.market_data.models import CandleGap

TIMEFRAME_INTERVALS_MS: dict[Timeframe, int] = {
    Timeframe.M15: 15 * 60 * 1000,  # 900,000 ms
    Timeframe.H1: 60 * 60 * 1000,  # 3,600,000 ms
    Timeframe.H4: 4 * 60 * 60 * 1000,  # 14,400,000 ms
    Timeframe.D1: 24 * 60 * 60 * 1000,  # 86,400,000 ms
}


class GapDetector:
    """Monitors candle sequences and flags missing intervals."""

    def __init__(self) -> None:
        self.health = MarketDataHealth.HEALTHY
        self._last_open_times: dict[Timeframe, int] = {}

    def check_candle(self, candle: Candle) -> CandleGap | None:
        """Evaluate a newly received completed candle for sequence continuity."""
        interval = TIMEFRAME_INTERVALS_MS.get(candle.timeframe, 900000)
        tf = candle.timeframe

        if tf in self._last_open_times:
            prev_open = self._last_open_times[tf]
            # Normal duplicate or older candle
            if candle.open_time <= prev_open:
                return None

            expected_open = prev_open + interval
            if candle.open_time > expected_open:
                self.health = MarketDataHealth.GAP_DETECTED
                self._last_open_times[tf] = candle.open_time
                return CandleGap(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    expected_open_time=expected_open,
                    actual_open_time=candle.open_time,
                    detected_at=int(time.time() * 1000),
                )

        self._last_open_times[tf] = candle.open_time
        self.health = MarketDataHealth.HEALTHY
        return None

    def mark_recovered(self) -> None:
        """Transition health back to HEALTHY once missing gaps have been recovered."""
        self.health = MarketDataHealth.HEALTHY
