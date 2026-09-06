"""Paper and shadow trading domain models."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import PositionSnapshot


class TradingMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE = "LIVE"


class PaperAccount(BaseModel):
    """Immutable snapshot of paper trading account state."""

    model_config = ConfigDict(frozen=True)

    paper_wallet_balance: Decimal = Field(..., ge=Decimal("0"))
    paper_position: PositionSnapshot | None = None
    paper_realized_pnl: Decimal = Decimal("0.0")
    paper_total_trades: int = 0


class PreFlightReport(BaseModel):
    """Audit report from 10-point pre-flight safety checklist."""

    model_config = ConfigDict(frozen=True)

    is_ready_for_paper: bool
    is_ready_for_live: bool
    checklist_results: dict[str, bool]
    summary: str
