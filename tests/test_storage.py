"""Tests for SQLite persistence foundation and immutable decision snapshots."""

from decimal import Decimal
from pathlib import Path

import pytest

from src.domain.enums import DecisionState, MarketRegime, Timeframe
from src.domain.models import Candle, DecisionSnapshot
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

    expected_tables = {"decision_snapshots", "orders", "positions", "audit_events", "candles"}
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
        indicators={"rsi": "45.5", "adx": "22.0"},
        risk_state={"liquidation_ok": True, "exposure": "0.00"},
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
    assert retrieved.indicators["rsi"] == "45.5"


@pytest.mark.asyncio
async def test_financial_precision_preserved_in_storage(tmp_path: Path) -> None:
    """Financial fields stored in SQLite as TEXT must retain exact Decimal precision."""
    db_file = tmp_path / "test_precision.db"
    db = DatabaseManager(str(db_file))
    await db.initialize()

    # Exact decimal precision with many decimal places
    precise_amount = Decimal("2700.12345678")

    async with db.connection() as conn:
        await conn.execute(
            """
            INSERT INTO orders (
                order_id, client_order_id, symbol, side, order_type,
                quantity, price, notional, is_dca, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                "ord_1",
                "cl_1",
                "XAUUSDT",
                "BUY",
                "LIMIT",
                str(Decimal("0.50000000")),
                str(precise_amount),
                str(Decimal("1350.06172839")),
                0,
                "NEW",
            ),
        )
        await conn.commit()

        cursor = await conn.execute("SELECT price, notional FROM orders WHERE order_id = 'ord_1';")
        row = await cursor.fetchone()
        assert row is not None
        assert Decimal(row[0]) == precise_amount
        assert Decimal(row[1]) == Decimal("1350.06172839")


@pytest.mark.asyncio
async def test_save_and_retrieve_candles(tmp_path: Path) -> None:
    """Candles must be persisted to SQLite with exact Decimal values and retrieved in order."""
    db_file = tmp_path / "test_candles.db"
    db = DatabaseManager(str(db_file))
    await db.initialize()

    c1 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000000000,
        open=Decimal("2700.12"),
        high=Decimal("2710.50"),
        low=Decimal("2695.80"),
        close=Decimal("2705.40"),
        volume=Decimal("150.123456"),
        close_time=1700000899999,
        is_closed=True,
    )
    c2 = Candle(
        symbol="XAUUSDT",
        timeframe=Timeframe.M15,
        open_time=1700000900000,
        open=Decimal("2705.40"),
        high=Decimal("2715.00"),
        low=Decimal("2702.00"),
        close=Decimal("2712.00"),
        volume=Decimal("180.500000"),
        close_time=1700001799999,
        is_closed=True,
    )

    await db.save_candle(c1)
    await db.save_candle(c2)

    retrieved = await db.get_candles("XAUUSDT", Timeframe.M15)
    assert len(retrieved) == 2
    assert retrieved[0].open == Decimal("2700.12")
    assert retrieved[0].volume == Decimal("150.123456")
    assert retrieved[1].close == Decimal("2712.00")
    assert retrieved[0].open_time < retrieved[1].open_time
