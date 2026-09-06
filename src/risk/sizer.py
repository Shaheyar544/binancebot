"""Position sizer with Decimal quantization and DCA invariant enforcement."""

from decimal import ROUND_DOWN, Decimal

from src.domain.enums import OrderSide
from src.domain.models import MAX_DCA_NOTIONAL, OrderIntent
from src.exchange.metadata import SymbolFilters


class PositionSizer:
    """Computes and quantizes order size strictly according to exchange filters and limits."""

    def __init__(self, filters: SymbolFilters) -> None:
        self.filters = filters

    def quantize_price(self, price: Decimal) -> Decimal:
        """Quantize price to the tick_size without binary float drift."""
        # Use quantize with the tick_size pattern
        return price.quantize(self.filters.tick_size, rounding=ROUND_DOWN)

    def quantize_quantity(self, quantity: Decimal) -> Decimal:
        """Floor quantity to step_size to prevent accidental over-sizing."""
        return quantity.quantize(self.filters.step_size, rounding=ROUND_DOWN)

    def create_entry_intent(
        self,
        price: Decimal,
        target_notional: Decimal,
        client_order_id: str,
        reason: str,
    ) -> OrderIntent:
        """Build a quantized long opening OrderIntent."""
        quantized_price = self.quantize_price(price)
        raw_qty = target_notional / quantized_price
        quantized_qty = self.quantize_quantity(raw_qty)
        actual_notional = quantized_qty * quantized_price

        if actual_notional < self.filters.min_notional:
            raise ValueError(
                f"Order notional below minimum "
                f"(${actual_notional:.2f} < ${self.filters.min_notional:.2f})"
            )

        if quantized_qty < self.filters.min_qty:
            raise ValueError(
                f"Order quantity below minimum ({quantized_qty} < {self.filters.min_qty})"
            )

        return OrderIntent(
            symbol=self.filters.symbol,
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=quantized_qty,
            price=quantized_price,
            notional=actual_notional,
            is_dca=False,
            is_opening=True,
            client_order_id=client_order_id,
            reason=reason,
        )

    def create_dca_intent(
        self,
        price: Decimal,
        requested_notional: Decimal,
        client_order_id: str,
        reason: str,
    ) -> OrderIntent:
        """Build a quantized DCA OrderIntent enforcing the MAX_DCA_NOTIONAL limit."""
        if requested_notional > MAX_DCA_NOTIONAL:
            raise ValueError(
                f"DCA order notional cannot exceed $500: received ${requested_notional:.2f}"
            )

        quantized_price = self.quantize_price(price)
        raw_qty = requested_notional / quantized_price
        quantized_qty = self.quantize_quantity(raw_qty)
        actual_notional = quantized_qty * quantized_price

        if actual_notional > MAX_DCA_NOTIONAL:
            raise ValueError(
                f"DCA order notional cannot exceed $500: received ${actual_notional:.2f}"
            )

        if actual_notional < self.filters.min_notional:
            raise ValueError(
                f"Order notional below minimum "
                f"(${actual_notional:.2f} < ${self.filters.min_notional:.2f})"
            )

        return OrderIntent(
            symbol=self.filters.symbol,
            side=OrderSide.BUY,
            order_type="LIMIT",
            quantity=quantized_qty,
            price=quantized_price,
            notional=actual_notional,
            is_dca=True,
            is_opening=True,
            client_order_id=client_order_id,
            reason=reason,
        )
