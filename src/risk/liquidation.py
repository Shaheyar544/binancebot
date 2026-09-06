"""Exchange-specific liquidation estimation abstractions.

Invariant (AGENTS.md Section 5 & 14):
Never invent or rely on a simplified generic liquidation formula for live or authoritative
risk decisions. If reliable exchange information (maintenance margin brackets, account equity,
cross-collateral tiers) is unavailable, liquidation safety MUST be marked UNAVAILABLE or
BLOCKED rather than guessing.
"""

from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class LiquidationSafetyStatus(StrEnum):
    """Explicit status of liquidation safety evaluation."""

    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNAVAILABLE = "UNAVAILABLE"


class LiquidationEstimateResult:
    """Immutable result of a liquidation price evaluation."""

    def __init__(
        self,
        status: LiquidationSafetyStatus,
        liquidation_price: Decimal | None,
        reason: str,
    ) -> None:
        self.status = status
        self.liquidation_price = liquidation_price
        self.reason = reason

    @property
    def is_safe(self) -> bool:
        return self.status == LiquidationSafetyStatus.SAFE

    def __repr__(self) -> str:
        return (
            f"LiquidationEstimateResult(status={self.status}, "
            f"price={self.liquidation_price}, reason='{self.reason}')"
        )


class ExchangeLiquidationEstimator(Protocol):
    """Authoritative exchange-specific liquidation estimator protocol."""

    def evaluate_liquidation(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
        max_acceptable_price: Decimal,
    ) -> LiquidationEstimateResult:
        """Evaluate whether prospective position liquidation price satisfies safety threshold."""
        ...

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal | None:
        """Estimate numeric liquidation price if authoritative inputs are present, else None."""
        ...


class UnavailableLiquidationEstimator:
    """Estimator used when authoritative Binance margin tiers/account collateral are unavailable.

    Strictly refuses to fabricate generic formulas and marks liquidation safety as UNAVAILABLE.
    """

    def __init__(self, reason: str = "Authoritative exchange margin tiers unavailable") -> None:
        self.reason = reason

    def evaluate_liquidation(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
        max_acceptable_price: Decimal,
    ) -> LiquidationEstimateResult:
        return LiquidationEstimateResult(
            status=LiquidationSafetyStatus.UNAVAILABLE,
            liquidation_price=None,
            reason=self.reason,
        )

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal | None:
        return None


class ConfigurableLiquidationEstimator:
    """Testable and policy-configurable liquidation estimator.

    Allows explicit backtest modeling with defined safety status or explicit bounds,
    ensuring tests can verify behavior under SAFE, UNSAFE, and UNAVAILABLE states.
    """

    def __init__(
        self,
        fixed_price: Decimal | None = None,
        forced_status: LiquidationSafetyStatus | None = None,
        reason: str = "Configured test liquidation estimator",
    ) -> None:
        self.fixed_price = fixed_price
        self.forced_status = forced_status
        self.reason = reason

    def evaluate_liquidation(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
        max_acceptable_price: Decimal,
    ) -> LiquidationEstimateResult:
        if self.forced_status is not None:
            return LiquidationEstimateResult(
                status=self.forced_status,
                liquidation_price=self.fixed_price,
                reason=self.reason,
            )

        if self.fixed_price is None:
            return LiquidationEstimateResult(
                status=LiquidationSafetyStatus.UNAVAILABLE,
                liquidation_price=None,
                reason="No authoritative liquidation price configured",
            )

        if self.fixed_price > max_acceptable_price:
            return LiquidationEstimateResult(
                status=LiquidationSafetyStatus.UNSAFE,
                liquidation_price=self.fixed_price,
                reason=("Estimated liquidation () exceeds acceptable threshold ()"),
            )

        return LiquidationEstimateResult(
            status=LiquidationSafetyStatus.SAFE,
            liquidation_price=self.fixed_price,
            reason="Estimated liquidation () meets safety requirements",
        )

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal | None:
        return self.fixed_price
