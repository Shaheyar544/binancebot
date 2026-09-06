"""Domain protocols and abstract interfaces."""

from decimal import Decimal
from typing import Protocol


class LiquidationEstimator(Protocol):
    """Domain protocol for liquidation price estimation.

    Concrete implementations for Binance will be built in the exchange integration phase
    using live account, margin, and tier structures.
    """

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal | None:
        """Estimate the liquidation price for a position, or None if unavailable."""
        ...
