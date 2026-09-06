"""Dashboard response schemas for read-only observability."""

from pydantic import BaseModel, ConfigDict

from src.domain.enums import DecisionState, MarketRegime
from src.macro.models import NewsLockState
from src.market_data.enums import MarketDataHealth


class HealthResponse(BaseModel):
    """System health and gate status report."""

    model_config = ConfigDict(frozen=True)

    status: str
    live_trading_enabled: bool
    data_health: MarketDataHealth
    news_lock_state: NewsLockState
    timestamp: int


class OverviewResponse(BaseModel):
    """Current market condition snapshot."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    last_price: str
    mark_price: str
    index_price: str
    funding_rate: str
    regime: MarketRegime
    timestamp: int


class DecisionSummaryResponse(BaseModel):
    """Summary of historical engine decision snapshot."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    timestamp: int
    decision_state: DecisionState
    regime: MarketRegime
    reason: str
