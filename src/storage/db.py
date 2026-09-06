"""SQLite persistence layer for immutable snapshots and audit logs."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import aiosqlite

from src.domain.enums import DecisionState, MarketRegime, Timeframe
from src.domain.models import Candle, DecisionSnapshot


class DatabaseManager:
    """Async manager for SQLite database persistence."""

    def __init__(self, db_path: str = "xau_bot.db") -> None:
        self.db_path = db_path

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Provide an active async connection to the database."""
        conn = await aiosqlite.connect(self.db_path)
        try:
            yield conn
        finally:
            await conn.close()

    async def initialize(self) -> None:
        """Initialize database schema with all required tables."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        async with self.connection() as conn:
            await conn.execute("PRAGMA journal_mode=WAL;")
            await conn.execute("PRAGMA foreign_keys=ON;")

            # Table for immutable decision snapshots
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS decision_snapshots (
                    decision_id TEXT PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    decision_state TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    indicators_json TEXT NOT NULL,
                    risk_state_json TEXT NOT NULL,
                    event_state_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Table for orders
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    quantity TEXT NOT NULL,
                    price TEXT NOT NULL,
                    notional TEXT NOT NULL,
                    is_dca INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Table for positions
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    size TEXT NOT NULL,
                    entry_price TEXT NOT NULL,
                    leverage TEXT NOT NULL,
                    liquidation_price TEXT NOT NULL,
                    unrealized_pnl TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )

            # Table for audit events
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            # Table for canonical candles
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    open_time INTEGER NOT NULL,
                    open TEXT NOT NULL,
                    high TEXT NOT NULL,
                    low TEXT NOT NULL,
                    close TEXT NOT NULL,
                    volume TEXT NOT NULL,
                    close_time INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, timeframe, open_time)
                );
                """
            )

            await conn.commit()

    async def save_decision_snapshot(self, snapshot: DecisionSnapshot) -> None:
        """Persist an immutable decision snapshot to the database."""
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO decision_snapshots (
                    decision_id, timestamp, decision_state, regime,
                    indicators_json, risk_state_json, event_state_json,
                    reason, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    snapshot.decision_id,
                    snapshot.timestamp,
                    snapshot.decision_state.value,
                    snapshot.regime.value,
                    json.dumps(snapshot.indicators),
                    json.dumps(snapshot.risk_state),
                    json.dumps(snapshot.event_state),
                    snapshot.reason,
                    snapshot.source,
                ),
            )
            await conn.commit()

    async def get_decision_snapshot(self, decision_id: str) -> DecisionSnapshot | None:
        """Retrieve a decision snapshot by its ID."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT decision_id, timestamp, decision_state, regime,
                       indicators_json, risk_state_json, event_state_json,
                       reason, source
                FROM decision_snapshots
                WHERE decision_id = ?;
                """,
                (decision_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None

            return DecisionSnapshot(
                decision_id=row[0],
                timestamp=row[1],
                decision_state=DecisionState(row[2]),
                regime=MarketRegime(row[3]),
                indicators=json.loads(row[4]),
                risk_state=json.loads(row[5]),
                event_state=json.loads(row[6]),
                reason=row[7],
                source=row[8],
            )

    async def get_recent_decisions(self, limit: int = 50) -> list[DecisionSnapshot]:
        """Retrieve latest decision snapshots ordered by timestamp descending."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT decision_id, timestamp, decision_state, regime,
                       indicators_json, risk_state_json, event_state_json,
                       reason, source
                FROM decision_snapshots
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                DecisionSnapshot(
                    decision_id=row[0],
                    timestamp=row[1],
                    decision_state=DecisionState(row[2]),
                    regime=MarketRegime(row[3]),
                    indicators=json.loads(row[4]),
                    risk_state=json.loads(row[5]),
                    event_state=json.loads(row[6]),
                    reason=row[7],
                    source=row[8],
                )
                for row in rows
            ]

    async def save_candle(self, candle: Candle) -> None:
        """Persist a completed canonical candle to SQLite."""
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO candles (
                    symbol, timeframe, open_time, open, high, low, close, volume, close_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    candle.symbol,
                    candle.timeframe.value,
                    candle.open_time,
                    str(candle.open),
                    str(candle.high),
                    str(candle.low),
                    str(candle.close),
                    str(candle.volume),
                    candle.close_time,
                ),
            )
            await conn.commit()

    async def get_candles(
        self, symbol: str, timeframe: Timeframe, limit: int = 500
    ) -> list[Candle]:
        """Retrieve historical candles for a symbol and timeframe sorted chronologically."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT symbol, timeframe, open_time, open, high, low, close, volume, close_time
                FROM candles
                WHERE symbol = ? AND timeframe = ?
                ORDER BY open_time ASC
                LIMIT ?;
                """,
                (symbol, timeframe.value, limit),
            )
            rows = await cursor.fetchall()
            return [
                Candle(
                    symbol=row[0],
                    timeframe=Timeframe(row[1]),
                    open_time=row[2],
                    open=Decimal(row[3]),
                    high=Decimal(row[4]),
                    low=Decimal(row[5]),
                    close=Decimal(row[6]),
                    volume=Decimal(row[7]),
                    close_time=row[8],
                    is_closed=True,
                )
                for row in rows
            ]
