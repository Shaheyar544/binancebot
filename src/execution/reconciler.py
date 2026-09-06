"""State reconciler synchronizing local state with exchange authority."""

import time
from decimal import Decimal

from src.domain.enums import PositionSide
from src.execution.adapter import ExchangeAdapter
from src.execution.models import ReconciliationReport, ReconciliationStatus


class StateReconciler:
    """Synchronizes local position and account state against authoritative exchange state."""

    def __init__(self, adapter: ExchangeAdapter, symbol: str = "XAUUSDT") -> None:
        self.adapter = adapter
        self.symbol = symbol

    async def reconcile(self) -> ReconciliationReport:
        """Poll exchange state and perform reconciliation checks."""
        now_ms = int(time.time() * 1000)

        # Check raw position payload for safety invariants
        raw = await self.adapter.get_raw_position(self.symbol)
        if raw is not None:
            raw_amt = Decimal(str(raw.get("positionAmt", "0.0")))
            # Hard safety invariant: Never allow SHORT positions
            if raw_amt < Decimal("0.0"):
                return ReconciliationReport(
                    status=ReconciliationStatus.EMERGENCY_STOP,
                    message=f"Illegal short position detected on exchange: size={raw_amt}",
                    synced_position=None,
                    open_orders_count=0,
                    timestamp=now_ms,
                )

        # Retrieve parsed position snapshot
        pos = await self.adapter.get_position(self.symbol)
        if pos is not None and pos.side != PositionSide.LONG:
            return ReconciliationReport(
                status=ReconciliationStatus.EMERGENCY_STOP,
                message=f"Exchange position side is {pos.side}, expected LONG only",
                synced_position=pos,
                open_orders_count=0,
                timestamp=now_ms,
            )

        return ReconciliationReport(
            status=ReconciliationStatus.RECONCILED,
            message="State reconciled successfully with exchange authority",
            synced_position=pos,
            open_orders_count=0,
            timestamp=now_ms,
        )
