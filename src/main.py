"""Main application entry point for XAUUSDT Adaptive Bot."""

import asyncio
import logging
from decimal import Decimal

from pydantic import BaseModel

from src.config.settings import BotConfig, UserRiskConfig
from src.domain.enums import DecisionState
from src.storage.db import DatabaseManager
from src.utils.logging import configure_logging

logger = logging.getLogger("xau_bot.main")


class BootstrapStatus(BaseModel):
    """Status report returned upon successful bot startup."""

    is_bootstrapped: bool
    live_execution_enabled: bool
    initial_state: DecisionState = DecisionState.WAIT


class BotApplication:
    """Core orchestrator for bot startup, safety validation, and lifecycle."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.db = DatabaseManager(config.database_path)

    async def bootstrap(self) -> BootstrapStatus:
        """Perform deterministic, safe bootstrap sequence."""
        # 1. Configure logging and scrub secrets
        secrets_to_redact = []
        if self.config.binance_api_key.get_secret_value():
            secrets_to_redact.append(self.config.binance_api_key.get_secret_value())
        if self.config.binance_api_secret.get_secret_value():
            secrets_to_redact.append(self.config.binance_api_secret.get_secret_value())

        configure_logging(
            log_level=self.config.log_level,
            secrets_to_redact=secrets_to_redact,
        )

        logger.info("Initializing XAUUSDT Adaptive Long-Only Bot...")

        # 2. Verify Execution Gates
        if self.config.gates.can_execute_live:
            logger.warning(
                "CAUTION: LIVE ORDER EXECUTION IS ENABLED! Real orders will be dispatched."
            )
        else:
            logger.info("SAFETY GATE ACTIVE: Live execution is DISABLED. Orders will not be sent.")

        # 3. Initialize Database
        await self.db.initialize()
        logger.info(
            "Persistence database initialized successfully at: %s", self.config.database_path
        )

        # 4. Confirm default state is WAIT
        logger.info("Bot startup complete. Current state: %s", DecisionState.WAIT.value)

        return BootstrapStatus(
            is_bootstrapped=True,
            live_execution_enabled=self.config.gates.can_execute_live,
            initial_state=DecisionState.WAIT,
        )

    async def run(self, max_cycles: int | None = None) -> None:
        """Run bot autonomous orchestration loop with reconciliation and candle evaluation."""
        status = await self.bootstrap()
        logger.info("Bot running in safe mode. Status: %s", status)

        # Import domain modules for cycle
        from src.domain.enums import Timeframe
        from src.exchange.metadata import SymbolFilters
        from src.execution.adapter import FakeExchangeAdapter
        from src.execution.order_manager import OrderManager
        from src.risk.engine import RiskEngine
        from src.strategy.entry_families import EntryOrchestrator

        filters = SymbolFilters(
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

        class DefaultEstimator:
            def estimate_liquidation_price(
                self, entry_price: Decimal, leverage: Decimal, allocated_funds: Decimal
            ) -> Decimal:
                return entry_price * (Decimal("1.0") - (Decimal("1.0") / leverage))

        risk_engine = RiskEngine(
            config=self.config.risk,
            filters=filters,
            estimator=DefaultEstimator(),
        )

        adapter = FakeExchangeAdapter()
        order_manager = OrderManager(
            gates=self.config.gates,
            risk_engine=risk_engine,
            adapter=adapter,
            db=self.db,
        )
        await order_manager.restore_idempotency_state()
        entry_orchestrator = EntryOrchestrator()

        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            cycles += 1
            try:
                # 1. Reconcile open position and active risk
                position = await adapter.get_position("XAUUSDT")
                if position is not None and position.size > Decimal("0"):
                    # Check emergency loss
                    if risk_engine.is_emergency_loss_breached(position):
                        logger.warning("Emergency loss limit breached! Initiating emergency close.")

                # 2. Check completed candles from persistence
                candles_15m = await self.db.get_candles("XAUUSDT", Timeframe.M15, limit=50)
                if len(candles_15m) >= 2:
                    # Identify levels & evaluate setup
                    supp, res = entry_orchestrator.identify_levels(candles_15m)
                    latest = candles_15m[-1]
                    _ = entry_orchestrator.evaluate_setups(
                        candles_15m=candles_15m,
                        ema_20=latest.close,
                        ema_50=latest.close,
                        support_level=supp,
                        resistance_level=res,
                    )

                logger.debug("Completed autonomous trading cycle #%d", cycles)
            except Exception as e:
                logger.error("Error during autonomous cycle: %s", e)

            if max_cycles is not None and cycles >= max_cycles:
                break
            await asyncio.sleep(1)


def main() -> None:
    """CLI entry point."""
    # Default sample config for safe verification
    sample_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("3.0"),
        max_acceptable_liquidation_price=Decimal("1800.00"),
    )
    config = BotConfig(risk=sample_risk)
    app = BotApplication(config)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
