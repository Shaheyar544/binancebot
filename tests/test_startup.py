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


@pytest.mark.asyncio
async def test_no_order_placement_or_exchange_connection_in_this_phase(
    tmp_path: Path,
) -> None:
    """Startup must never connect to live exchange or attempt order submission."""
    db_path = str(tmp_path / "startup_safety.db")
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

    # Zero orders in DB
    async with app.db.connection() as conn:
        cursor = await conn.execute("SELECT COUNT(*) FROM orders;")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == 0

    assert status.live_execution_enabled is False


@pytest.mark.asyncio
async def test_bot_application_run_cycle(tmp_path: Path) -> None:
    """BotApplication.run executes clean autonomous cycle and completes without error."""
    db_path = str(tmp_path / "cycle_test.db")
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
    # Run exactly 1 autonomous cycle
    await app.run(max_cycles=1)
    assert Path(db_path).exists()
