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
        if self.config.binance_api_key:
            secrets_to_redact.append(self.config.binance_api_key)
        if self.config.binance_api_secret:
            secrets_to_redact.append(self.config.binance_api_secret)

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

    async def run(self) -> None:
        """Run bot lifecycle."""
        status = await self.bootstrap()
        logger.info("Bot running in safe mode. Status: %s", status)


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
