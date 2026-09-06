"""Canonical in-memory store for completed candles across timeframes."""

from collections import defaultdict

from src.domain.enums import Timeframe
from src.domain.models import Candle


class CanonicalCandleStore:
    """Stores validated, completed candles chronologically.

    Incomplete candles are strictly rejected from entering this store.
    Duplicates with identical open_times are handled idempotently.
    """

    def __init__(self) -> None:
        # Structure: timeframe -> {open_time: Candle}
        self._candles: dict[Timeframe, dict[int, Candle]] = defaultdict(dict)

    def add_candle(self, candle: Candle) -> None:
        """Add a completed candle to the store. Rejects in-progress candles."""
        if not candle.is_closed:
            raise ValueError(
                f"Incomplete candle cannot enter canonical store: "
                f"{candle.symbol} {candle.timeframe} at {candle.open_time}"
            )

        self._candles[candle.timeframe][candle.open_time] = candle

    def get_completed_candles(self, timeframe: Timeframe, count: int | None = None) -> list[Candle]:
        """Retrieve completed candles sorted chronologically by open_time."""
        timeframe_candles = self._candles[timeframe]
        sorted_candles = [timeframe_candles[t] for t in sorted(timeframe_candles.keys())]
        if count is not None:
            return sorted_candles[-count:]
        return sorted_candles

    def latest_completed(self, timeframe: Timeframe) -> Candle | None:
        """Retrieve the most recently completed candle for a timeframe."""
        candles = self.get_completed_candles(timeframe)
        return candles[-1] if candles else None

    def clear(self) -> None:
        """Clear the store."""
        self._candles.clear()
