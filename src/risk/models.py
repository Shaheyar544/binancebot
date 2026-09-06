"""Risk domain models for account metrics, rejection reasons, and check results."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import OrderIntent


class RiskRejectionReason(StrEnum):
    """Explicit reasons for trade rejection by the RiskEngine."""

    EXCEEDS_MAX_EXPOSURE = "EXCEEDS_MAX_EXPOSURE"
    EXCEEDS_MAX_ENTRIES = "EXCEEDS_MAX_ENTRIES"
    EXCEEDS_DAILY_LOSS_LIMIT = "EXCEEDS_DAILY_LOSS_LIMIT"
    EXCEEDS_EMERGENCY_LOSS_LIMIT = "EXCEEDS_EMERGENCY_LOSS_LIMIT"
    EXCEEDS_DCA_NOTIONAL_LIMIT = "EXCEEDS_DCA_NOTIONAL_LIMIT"
    UNSAFE_LIQUIDATION_PRICE = "UNSAFE_LIQUIDATION_PRICE"
    LIQUIDATION_INFO_UNAVAILABLE = "LIQUIDATION_INFO_UNAVAILABLE"
    BELOW_MIN_NOTIONAL = "BELOW_MIN_NOTIONAL"
    EXCHANGE_FILTER_VIOLATION = "EXCHANGE_FILTER_VIOLATION"
    DECISION_NOT_ACTIONABLE = "DECISION_NOT_ACTIONABLE"


class AccountRiskState(BaseModel):
    """Immutable snapshot of account financial and exposure state."""

    model_config = ConfigDict(frozen=True)

    wallet_balance: Decimal = Field(..., ge=Decimal("0"))
    available_balance: Decimal = Field(..., ge=Decimal("0"))
    total_open_exposure: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    realized_daily_loss: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    unrealized_pnl: Decimal = Field(default=Decimal("0"))
    open_entries_count: int = Field(default=0, ge=0)


class RiskCheckResult(BaseModel):
    """Outcome of a RiskEngine evaluation.

    Contains either an approved OrderIntent or an explicit rejection reason.
    """

    model_config = ConfigDict(frozen=True)

    is_approved: bool
    rejection_reason: RiskRejectionReason | None = None
    explanation: str
    approved_intent: OrderIntent | None = None
