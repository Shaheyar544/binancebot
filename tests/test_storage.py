"""Tests for SQLite persistence foundation and immutable decision snapshots."""

from pathlib import Path

import pytest

from src.domain.enums import DecisionState, MarketRegime
from src.domain.models import DecisionSnapshot
from src.storage.db import DatabaseManager


@pytest.mark.asyncio
async def test_database_initialization(tmp_path: Path) -> None:
    """Database schema must initialize all required tables."""
    db_file = tmp_path / "test_bot.db"
    db = DatabaseManager(str(db_file))
    await db.initialize()

    async with db.connection() as conn:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        )
        rows = await cursor.fetchall()
        tables = {row[0] for row in rows}

    expected_tables = {"decision_snapshots", "orders", "positions", "audit_events"}
    assert expected_tables.issubset(tables)


@pytest.mark.asyncio
async def test_save_and_retrieve_decision_snapshot(tmp_path: Path) -> None:
    """Decision snapshot must be saved immutably with exact evidence and retrieved accurately."""
    db_file = tmp_path / "test_bot.db"
    db = DatabaseManager(str(db_file))
    await db.initialize()

    snapshot = DecisionSnapshot(
        decision_id="snap_001",
        timestamp=1700000000000,
        decision_state=DecisionState.WAIT,
        regime=MarketRegime.BULLISH_RANGE,
        indicators={"rsi": 45.5, "adx": 22.0},
        risk_state={"liquidation_ok": True, "exposure": 0.0},
        event_state={"in_news_lock": False},
        reason="Score 78 below entry threshold 85",
        source="StrategyEngine",
    )

    await db.save_decision_snapshot(snapshot)

    retrieved = await db.get_decision_snapshot("snap_001")
    assert retrieved is not None
    assert retrieved.decision_id == "snap_001"
    assert retrieved.decision_state == DecisionState.WAIT
    assert retrieved.regime == MarketRegime.BULLISH_RANGE
    assert retrieved.reason == "Score 78 below entry threshold 85"
    assert retrieved.indicators["rsi"] == 45.5
