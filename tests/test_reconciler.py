"""Tests for StateReconciler: startup check, position sync, and short-side emergency stop."""

from decimal import Decimal

import pytest

from src.domain.enums import PositionSide
from src.domain.models import PositionSnapshot
from src.execution.adapter import FakeExchangeAdapter
from src.execution.models import ReconciliationStatus
from src.execution.reconciler import StateReconciler


@pytest.mark.asyncio
async def test_reconciler_synchronizes_clean_position() -> None:
    """When exchange has long position, reconciler updates local state successfully."""
    adapter = FakeExchangeAdapter()
    exchange_pos = PositionSnapshot(
        symbol="XAUUSDT",
        side=PositionSide.LONG,
        size=Decimal("1.5"),
        entry_price=Decimal("2710.00"),
        leverage=Decimal("5.0"),
        margin=Decimal("813.00"),
        liquidation_price=Decimal("2400.00"),
        unrealized_pnl=Decimal("15.00"),
    )
    adapter.set_position(exchange_pos)

    reconciler = StateReconciler(adapter=adapter)
    report = await reconciler.reconcile()

    assert report.status == ReconciliationStatus.RECONCILED
    assert report.synced_position is not None
    assert report.synced_position.size == Decimal("1.5")


@pytest.mark.asyncio
async def test_reconciler_rejects_illegal_short_side() -> None:
    """If exchange adapter reports short position, trigger EMERGENCY_STOP."""
    adapter = FakeExchangeAdapter()
    adapter.inject_raw_short_state(
        symbol="XAUUSDT",
        size=Decimal("-1.0"),
        entry_price=Decimal("2710.00"),
    )

    reconciler = StateReconciler(adapter=adapter)
    report = await reconciler.reconcile()

    assert report.status == ReconciliationStatus.EMERGENCY_STOP
    assert "Illegal short position detected on exchange" in report.message
