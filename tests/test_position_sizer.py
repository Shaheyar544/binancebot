"""Tests for PositionSizer: exchange filter quantization and DCA ceiling enforcement."""

from decimal import Decimal

import pytest

from src.domain.enums import OrderSide
from src.exchange.metadata import SymbolFilters
from src.risk.sizer import PositionSizer


@pytest.fixture
def xau_filters() -> SymbolFilters:
    return SymbolFilters(
        symbol="XAUUSDT",
        status="TRADING",
        contract_type="PERPETUAL",
        base_asset="XAU",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=3,
        tick_size=Decimal("0.01"),
        min_price=Decimal("100.00"),
        max_price=Decimal("100000.00"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("1000.000"),
        min_notional=Decimal("5.0"),
    )


def test_quantize_price(xau_filters: SymbolFilters) -> None:
    """Price is rounded to the tick_size without binary float drift."""
    sizer = PositionSizer(filters=xau_filters)
    raw_price = Decimal("2715.6789")
    quantized = sizer.quantize_price(raw_price)
    assert quantized == Decimal("2715.67")


def test_quantize_quantity(xau_filters: SymbolFilters) -> None:
    """Quantity is floored to the step_size so order never exceeds intended risk."""
    sizer = PositionSizer(filters=xau_filters)
    raw_qty = Decimal("1.2348")
    quantized = sizer.quantize_quantity(raw_qty)
    assert quantized == Decimal("1.234")


def test_dca_size_at_or_below_500_allowed(xau_filters: SymbolFilters) -> None:
    """A DCA notional request <= $500.00 is allowed and sized."""
    sizer = PositionSizer(filters=xau_filters)
    price = Decimal("2700.00")

    # $500.00 exactly
    intent = sizer.create_dca_intent(
        price=price,
        requested_notional=Decimal("500.00"),
        client_order_id="DCA_001",
        reason="Test DCA 500",
    )
    assert intent.side == OrderSide.BUY
    assert intent.is_dca is True
    assert intent.notional <= Decimal("500.00")
    assert intent.notional >= Decimal("499.00")


def test_dca_size_exceeding_500_rejected(xau_filters: SymbolFilters) -> None:
    """A DCA notional request > $500.00 is rejected immediately and never split."""
    sizer = PositionSizer(filters=xau_filters)
    price = Decimal("2700.00")

    # $500.01 is blocked
    with pytest.raises(ValueError, match="DCA order notional cannot exceed \\$500"):
        sizer.create_dca_intent(
            price=price,
            requested_notional=Decimal("500.01"),
            client_order_id="DCA_002",
            reason="Test DCA 500.01",
        )

    # $700.00 is blocked
    with pytest.raises(ValueError, match="DCA order notional cannot exceed \\$500"):
        sizer.create_dca_intent(
            price=price,
            requested_notional=Decimal("700.00"),
            client_order_id="DCA_003",
            reason="Test DCA 700",
        )


def test_sub_min_notional_rejected(xau_filters: SymbolFilters) -> None:
    """Order with notional below exchange min_notional is rejected."""
    sizer = PositionSizer(filters=xau_filters)
    price = Decimal("2700.00")
    with pytest.raises(ValueError, match="Order notional below minimum"):
        sizer.create_entry_intent(
            price=price,
            target_notional=Decimal("3.0"),  # min_notional is 5.0
            client_order_id="ENTRY_TOO_SMALL",
            reason="Sub min notional",
        )
