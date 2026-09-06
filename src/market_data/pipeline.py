"""Market data pipeline orchestrating candle stores, gap detection, and price updates."""

import logging

from src.domain.enums import Timeframe
from src.domain.models import Candle
from src.exchange.client import BinanceRestClient
from src.market_data.enums import MarketDataHealth, PriceType
from src.market_data.gap_detector import GapDetector
from src.market_data.models import CandleGap, PriceUpdate
from src.market_data.normalizer import CandleNormalizer
from src.market_data.store import CanonicalCandleStore

logger = logging.getLogger("xau_bot.market_data.pipeline")


class MarketDataPipeline:
    """Central read-only coordinator for canonical market data.

    Manages canonical candle storage, sequence gap detection, real-time price tracking,
    and data health states. Contains zero execution capability.
    """

    def __init__(
        self,
        symbol: str = "XAUUSDT",
        rest_client: BinanceRestClient | None = None,
    ) -> None:
        self.symbol = symbol
        self.rest_client = rest_client
        self.store = CanonicalCandleStore()
        self.gap_detector = GapDetector()
        self.normalizer = CandleNormalizer()
        self.latest_prices: dict[PriceType, PriceUpdate] = {}
        self._active_gaps: list[CandleGap] = []

    @property
    def health(self) -> MarketDataHealth:
        """Expose current aggregate market data health."""
        return self.gap_detector.health

    def ingest_completed_candle(self, candle: Candle) -> None:
        """Ingest and validate a newly closed candle."""
        gap = self.gap_detector.check_candle(candle)
        if gap is not None:
            logger.warning("Detected candle sequence gap: %s", gap)
            self._active_gaps.append(gap)

        self.store.add_candle(candle)

    async def backfill_candle(self, candle: Candle) -> None:
        """Backfill a missing candle to resolve an active gap."""
        self.store.add_candle(candle)
        self._active_gaps = [
            g
            for g in self._active_gaps
            if not (g.timeframe == candle.timeframe and g.expected_open_time == candle.open_time)
        ]
        if not self._active_gaps:
            self.gap_detector.mark_recovered()
            logger.info("Successfully recovered candle gaps; state restored to HEALTHY")

    def get_completed_candles(self, timeframe: Timeframe, count: int | None = None) -> list[Candle]:
        """Retrieve completed canonical candles chronologically."""
        return self.store.get_completed_candles(timeframe, count=count)

    def update_price(self, price_update: PriceUpdate) -> None:
        """Record an incoming real-time price event."""
        self.latest_prices[price_update.price_type] = price_update
