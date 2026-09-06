"""Tests for Read-Only FastAPI Dashboard API."""

from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from src.config.settings import ExecutionGateConfig, UserRiskConfig
from src.dashboard.app import create_dashboard_app
from src.dashboard.service import DashboardStateService
from src.domain.enums import DecisionState, MarketRegime
from src.domain.models import DecisionSnapshot, MarketSnapshot
from src.market_data.enums import MarketDataHealth
from src.storage.db import DatabaseManager


@pytest.fixture
async def temp_db(tmp_path: Path) -> DatabaseManager:
    db_file = tmp_path / "test_dash.db"
    db = DatabaseManager(str(db_file))
    await db.initialize()
    return db


@pytest.fixture
def base_service(temp_db: DatabaseManager) -> DashboardStateService:
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
    )
    gates = ExecutionGateConfig()
    service = DashboardStateService(
        db=temp_db,
        user_risk=user_risk,
        gates=gates,
    )
    # Populate mock market snapshot
    service.update_market_snapshot(
        MarketSnapshot(
            symbol="XAUUSDT",
            timestamp=1700000000000,
            last_price=Decimal("2715.50"),
            mark_price=Decimal("2715.40"),
            index_price=Decimal("2715.30"),
            funding_rate=Decimal("0.0001"),
        )
    )
    service.update_regime(MarketRegime.STRONG_BULL)
    return service


@pytest.mark.asyncio
async def test_health_endpoint(base_service: DashboardStateService) -> None:
    """Health endpoint reports health, gate status, and data status."""
    app = create_dashboard_app(service=base_service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"
        assert data["live_trading_enabled"] is False
        assert data["data_health"] == MarketDataHealth.HEALTHY.value


@pytest.mark.asyncio
async def test_overview_endpoint(base_service: DashboardStateService) -> None:
    """Overview endpoint returns price, mark price, and active regime."""
    app = create_dashboard_app(service=base_service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "XAUUSDT"
        assert data["last_price"] == "2715.50"
        assert data["regime"] == MarketRegime.STRONG_BULL.value


@pytest.mark.asyncio
async def test_decisions_endpoint(
    base_service: DashboardStateService, temp_db: DatabaseManager
) -> None:
    """Decisions endpoint retrieves historical audit decisions from database."""
    # Insert decision snapshot
    snapshot = DecisionSnapshot(
        decision_id="DEC_DASH_001",
        symbol="XAUUSDT",
        timestamp=1700000000000,
        decision_state=DecisionState.BUY,
        regime=MarketRegime.STRONG_BULL,
        reason="High conviction setup",
    )
    await temp_db.save_decision_snapshot(snapshot)

    app = create_dashboard_app(service=base_service)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/decisions")
        assert resp.status_code == 200
        decisions = resp.json()
        assert len(decisions) >= 1
        assert decisions[0]["decision_id"] == "DEC_DASH_001"
        assert decisions[0]["decision_state"] == "BUY"


@pytest.mark.asyncio
async def test_no_mutating_endpoints_exist(base_service: DashboardStateService) -> None:
    """Verify that dashboard API strictly exposes only GET endpoints."""
    app = create_dashboard_app(service=base_service)
    for route in app.routes:
        methods: set[str] = set(getattr(route, "methods", set()))
        assert methods.issubset({"GET", "HEAD", "OPTIONS"}), f"Mutating route found: {route}"
