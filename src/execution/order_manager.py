"""OrderManager coordinating live execution gates, idempotency, and dispatch."""

import logging

from src.config.settings import ExecutionGateConfig
from src.domain.models import OrderIntent
from src.execution.adapter import ExchangeAdapter
from src.execution.models import OrderExecutionResult
from src.risk.engine import RiskEngine

logger = logging.getLogger("xau_bot.execution.order_manager")


class OrderManager:
    """Manages order lifecycle, enforcing live execution gates and idempotency."""

    def __init__(
        self,
        gates: ExecutionGateConfig,
        risk_engine: RiskEngine,
        adapter: ExchangeAdapter,
    ) -> None:
        self.gates = gates
        self.risk_engine = risk_engine
        self.adapter = adapter
        self._processed_client_ids: set[str] = set()
        self._is_reconciling = False

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

        # 4. Mark client_order_id as processed
        self._processed_client_ids.add(intent.client_order_id)

        # 5. Dispatch via adapter
        result = await self.adapter.submit_order(intent)
        return result
