"""Paper trading runner orchestrating real-time simulation without real orders."""

import logging

from src.config.settings import ExecutionGateConfig
from src.domain.enums import DecisionState
from src.domain.models import DecisionSnapshot, OrderIntent
from src.execution.adapter import FakeExchangeAdapter
from src.paper.models import PaperAccount, TradingMode
from src.risk.engine import RiskEngine
from src.storage.db import DatabaseManager
from src.strategy.engine import StrategyEngine

logger = logging.getLogger("xau_bot.paper.runner")


class PaperTradingRunner:
    """Coordinates paper/shadow trading execution loops with zero live order dispatch."""

    def __init__(
        self,
        mode: TradingMode,
        gates: ExecutionGateConfig,
        strategy_engine: StrategyEngine,
        risk_engine: RiskEngine,
        adapter: FakeExchangeAdapter,
        db: DatabaseManager,
    ) -> None:
        self.mode = mode
        self.gates = gates
        self.strategy_engine = strategy_engine
        self.risk_engine = risk_engine
        self.adapter = adapter
        self.db = db
        self.account = PaperAccount(
            paper_wallet_balance=risk_engine.config.allocated_funds,
        )

    async def handle_decision(self, decision: DecisionSnapshot, intent: OrderIntent | None) -> None:
        """Log decision and process synthetic paper order fill if approved."""
        await self.db.save_decision_snapshot(decision)

        if decision.decision_state == DecisionState.BUY and intent is not None:
            # Paper execution dispatches strictly to FakeExchangeAdapter
            exec_res = await self.adapter.submit_order(intent)
            logger.info("Executed synthetic paper trade: %s", exec_res)
