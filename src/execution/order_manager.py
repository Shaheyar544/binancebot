import logging
from decimal import Decimal

from src.config.settings import ExecutionGateConfig
from src.domain.enums import OrderSide
from src.domain.models import OrderIntent
from src.execution.adapter import ExchangeAdapter
from src.execution.models import ExecutionStatus, OrderExecutionResult
from src.risk.engine import RiskEngine

logger = logging.getLogger("xau_bot.execution.order_manager")


class OrderManager:
    """Manages order lifecycle, enforcing live execution gates and idempotency."""

    def __init__(
        self,
        gates: ExecutionGateConfig,
        risk_engine: RiskEngine,
        adapter: ExchangeAdapter,
        db: object | None = None,
    ) -> None:
        self.gates = gates
        self.risk_engine = risk_engine
        self.adapter = adapter
        self.db = db
        self._processed_client_ids: set[str] = set()
        self._is_reconciling = False

    async def restore_idempotency_state(self) -> None:
        """Restore processed client order IDs from database on startup/reconnect."""
        if self.db is not None and hasattr(self.db, "get_all_client_order_ids"):
            recovered = await self.db.get_all_client_order_ids()
            self._processed_client_ids.update(recovered)
            logger.info("Restored %d client order IDs into idempotency cache", len(recovered))

    def set_reconciling(self, is_reconciling: bool) -> None:
        """Set reconciliation state flag."""
        self._is_reconciling = is_reconciling

    async def dispatch_order(self, intent: OrderIntent) -> OrderExecutionResult:
        """Validate safety gates, idempotency, and dispatch order to exchange."""
        # 1. State check: Never dispatch while reconciling
        if self._is_reconciling:
            raise RuntimeError("Order submission blocked: state reconciliation active")

        # 2. Idempotency check: Duplicate client_order_id detection
        if intent.client_order_id in self._processed_client_ids:
            raise ValueError(
                f"Duplicate order intent detected: client_order_id '{intent.client_order_id}' "
                "has already been processed"
            )

        # 3. Live execution gates check (strictly fail-closed)
        self.gates.assert_execution_allowed()

        # 4. Mark client_order_id as processed in memory
        self._processed_client_ids.add(intent.client_order_id)

        # 5. Dispatch via adapter
        result = await self.adapter.submit_order(intent)

        # 6. Persist order details to database if db is available
        if self.db is not None and hasattr(self.db, "record_order"):
            try:
                await self.db.record_order(
                    order_id=result.exchange_order_id or intent.client_order_id,
                    client_order_id=intent.client_order_id,
                    symbol=intent.symbol,
                    side=intent.side.value,
                    order_type=intent.order_type,
                    quantity=intent.quantity,
                    price=intent.price,
                    notional=intent.notional,
                    is_dca=intent.is_dca,
                    status=result.status.value,
                )
            except Exception as e:
                logger.error("Failed to persist dispatched order to DB: %s", e)

        return result

    async def dispatch_with_protective_stop(
        self,
        entry_intent: OrderIntent,
        stop_price: Decimal,
    ) -> tuple[OrderExecutionResult, OrderExecutionResult | None]:
        """Dispatch entry order; if filled, establish exchange protective stop immediately."""
        # 1. Dispatch entry order
        entry_result = await self.dispatch_order(entry_intent)

        # 2. If entry did not fill, no protective stop needed yet
        if entry_result.status != ExecutionStatus.FILLED:
            return entry_result, None

        # 3. Create protective stop intent (reduce-only SELL)
        stop_intent = OrderIntent(
            symbol=entry_intent.symbol,
            side=OrderSide.SELL,
            order_type="STOP_MARKET",
            quantity=entry_result.filled_qty,
            price=stop_price,
            notional=entry_result.filled_qty * stop_price,
            is_dca=False,
            is_opening=False,
            client_order_id=f"STOP_{entry_intent.client_order_id}",
            reason=f"Protective stop for entry {entry_intent.client_order_id}",
        )

        # 4. Dispatch protective stop order
        try:
            stop_result = await self.dispatch_order(stop_intent)
            return entry_result, stop_result
        except Exception as e:
            logger.critical(
                "CRITICAL: Entry filled (%s) but protective stop placement FAILED: %s! "
                "Entering emergency safety state.",
                entry_result.exchange_order_id,
                e,
            )
            # Re-raise to trigger emergency safety handler
            raise RuntimeError(
                f"Emergency protection failure: entry filled but protective stop failed: {e}"
            ) from e
