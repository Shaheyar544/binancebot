"""Tests for safe system startup and bootstrap."""

from decimal import Decimal
from pathlib import Path

import pytest

from src.config.settings import BotConfig, ExecutionGateConfig, UserRiskConfig
from src.domain.enums import DecisionState
from src.main import BotApplication


@pytest.mark.asyncio
async def test_safe_startup_with_disabled_gates(tmp_path: Path) -> None:
    """Safe startup must initialize cleanly, keep live execution disabled, and report ready."""
    db_path = str(tmp_path / "startup_test.db")
    config = BotConfig(
        gates=ExecutionGateConfig(live_trading=False, enable_order_execution=False),
        risk=UserRiskConfig(
            allocated_funds=Decimal("1000.00"),
            leverage=Decimal("3.0"),
            max_acceptable_liquidation_price=Decimal("1800.00"),
        ),
        database_path=db_path,
    )

    app = BotApplication(config)
    status = await app.bootstrap()

    assert status.is_bootstrapped is True
    assert status.live_execution_enabled is False
    assert status.initial_state == DecisionState.WAIT
    assert Path(db_path).exists()
