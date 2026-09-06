"""Read-only state aggregation service for dashboard queries."""

import time

from src.config.settings import ExecutionGateConfig, UserRiskConfig
from src.dashboard.models import DecisionSummaryResponse, HealthResponse, OverviewResponse
from src.domain.enums import MarketRegime
from src.domain.models import MarketSnapshot
from src.macro.event_manager import EconomicEventManager
from src.market_data.enums import MarketDataHealth
from src.storage.db import DatabaseManager


class DashboardStateService:
    """Provides aggregated read-only views over system state and database logs."""

    def __init__(
        self,
        db: DatabaseManager,
        user_risk: UserRiskConfig,
        gates: ExecutionGateConfig,
        event_manager: EconomicEventManager | None = None,
    ) -> None:
        self.db = db
        self.user_risk = user_risk
        self.gates = gates
        self.event_manager = event_manager or EconomicEventManager()
        self._market_snapshot: MarketSnapshot | None = None
        self._data_health: MarketDataHealth = MarketDataHealth.HEALTHY
        self._regime: MarketRegime = MarketRegime.NEUTRAL

    def update_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Update cached market snapshot."""
        self._market_snapshot = snapshot

    def update_data_health(self, health: MarketDataHealth) -> None:
        """Update market data health status."""
        self._data_health = health

    def update_regime(self, regime: MarketRegime) -> None:
        """Update current classified regime."""
        self._regime = regime

    def get_health(self) -> HealthResponse:
        """Return system health and safety gate state."""
        now_ms = int(time.time() * 1000)
        lock_state = self.event_manager.get_lock_state(now_ms)
        return HealthResponse(
            status="HEALTHY",
            live_trading_enabled=self.gates.can_execute_live,
            data_health=self._data_health,
            news_lock_state=lock_state,
            timestamp=now_ms,
        )

    def get_overview(self) -> OverviewResponse:
        """Return current market and regime overview."""
        now_ms = int(time.time() * 1000)
        snap = self._market_snapshot
        return OverviewResponse(
            symbol=snap.symbol if snap else "XAUUSDT",
            last_price=str(snap.last_price) if snap else "0.0",
            mark_price=str(snap.mark_price) if snap else "0.0",
            index_price=str(snap.index_price) if snap else "0.0",
            funding_rate=str(snap.funding_rate) if snap else "0.0",
            regime=self._regime,
            timestamp=snap.timestamp if snap else now_ms,
        )

    async def get_recent_decisions(self, limit: int = 50) -> list[DecisionSummaryResponse]:
        """Fetch latest decisions from SQLite audit database."""
        snapshots = await self.db.get_recent_decisions(limit=limit)
        return [
            DecisionSummaryResponse(
                decision_id=s.decision_id,
                timestamp=s.timestamp,
                decision_state=s.decision_state,
                regime=s.regime,
                reason=s.reason,
            )
            for s in snapshots
        ]
