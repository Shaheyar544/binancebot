"""Execution domain models: order status, fill records, and reconciliation reports."""

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from src.domain.models import PositionSnapshot


class ExecutionStatus(StrEnum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ReconciliationStatus(StrEnum):
    RECONCILED = "RECONCILED"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    ERROR = "ERROR"


class OrderExecutionResult(BaseModel):
    """Immutable outcome of an order execution dispatch."""

    model_config = ConfigDict(frozen=True)

    client_order_id: str
    exchange_order_id: str
    status: ExecutionStatus
    filled_qty: Decimal = Field(ge=Decimal("0"))
    avg_price: Decimal = Field(ge=Decimal("0"))
    fee_paid: Decimal = Field(default=Decimal("0.0"), ge=Decimal("0"))
    timestamp: int


class ReconciliationReport(BaseModel):
    """Immutable audit report from state reconciliation check."""

    model_config = ConfigDict(frozen=True)

    status: ReconciliationStatus
    message: str
    synced_position: PositionSnapshot | None = None
    open_orders_count: int = 0
    timestamp: int
