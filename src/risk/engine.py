"""RiskEngine coordinating user limits, liquidation safety, and position sizing."""

import uuid
from decimal import Decimal

from src.config.settings import UserRiskConfig
from src.domain.enums import DecisionState
from src.domain.interfaces import LiquidationEstimator
from src.domain.models import (
    MAX_DCA_NOTIONAL,
    DecisionSnapshot,
    PositionSnapshot,
)
from src.exchange.metadata import SymbolFilters
from src.risk.models import AccountRiskState, RiskCheckResult, RiskRejectionReason
from src.risk.sizer import PositionSizer


class RiskEngine:
    """Final authority before execution. Enforces all risk boundaries deterministically."""

    def __init__(
        self,
        config: UserRiskConfig,
        filters: SymbolFilters,
        estimator: LiquidationEstimator,
    ) -> None:
        self.config = config
        self.filters = filters
        self.estimator = estimator
        self.sizer = PositionSizer(filters=filters)

    def is_emergency_loss_breached(self, position: PositionSnapshot) -> bool:
        """Check if unrealized loss on position breaches emergency loss threshold."""
        if self.config.emergency_loss_limit is None:
            return False
        if position.unrealized_pnl < Decimal("0"):
            loss = abs(position.unrealized_pnl)
            return loss >= self.config.emergency_loss_limit
        return False

    def evaluate_entry(
        self,
        decision: DecisionSnapshot,
        current_price: Decimal,
        account_state: AccountRiskState,
        target_notional: Decimal,
    ) -> RiskCheckResult:
        """Evaluate prospective new long entry against all risk invariants."""
        # 1. State check
        if decision.decision_state != DecisionState.BUY:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.DECISION_NOT_ACTIONABLE,
                explanation=f"Candidate decision state is {decision.decision_state}, not BUY",
            )

        # 2. Realized daily loss limit
        if self.config.max_daily_loss is not None:
            if account_state.realized_daily_loss >= self.config.max_daily_loss:
                return RiskCheckResult(
                    is_approved=False,
                    rejection_reason=RiskRejectionReason.EXCEEDS_DAILY_LOSS_LIMIT,
                    explanation=(
                        f"Realized daily loss (${account_state.realized_daily_loss:.2f}) "
                        f"exceeds limit (${self.config.max_daily_loss:.2f})"
                    ),
                )

        # 3. Maximum total exposure limit
        if self.config.max_total_exposure is not None:
            projected_exposure = account_state.total_open_exposure + target_notional
            if projected_exposure > self.config.max_total_exposure:
                return RiskCheckResult(
                    is_approved=False,
                    rejection_reason=RiskRejectionReason.EXCEEDS_MAX_EXPOSURE,
                    explanation=(
                        f"Projected exposure (${projected_exposure:.2f}) "
                        f"exceeds limit (${self.config.max_total_exposure:.2f})"
                    ),
                )

        # 4. Maximum open entries limit
        if account_state.open_entries_count >= self.config.max_entries:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.EXCEEDS_MAX_ENTRIES,
                explanation=(
                    f"Open entries ({account_state.open_entries_count}) "
                    f"already at max ({self.config.max_entries})"
                ),
            )

        # 5. Liquidation price safety
        estimated_liq = self.estimator.estimate_liquidation_price(
            entry_price=current_price,
            leverage=self.config.leverage,
            allocated_funds=self.config.allocated_funds,
        )
        if estimated_liq > self.config.max_acceptable_liquidation_price:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.UNSAFE_LIQUIDATION_PRICE,
                explanation=(
                    f"Estimated liquidation price (${estimated_liq:.2f}) "
                    f"exceeds acceptable threshold "
                    f"(${self.config.max_acceptable_liquidation_price:.2f})"
                ),
            )

        # 6. Sizing and exchange filter validation
        try:
            client_id = f"BUY_{uuid.uuid4().hex[:8]}"
            intent = self.sizer.create_entry_intent(
                price=current_price,
                target_notional=target_notional,
                client_order_id=client_id,
                reason=decision.reason,
            )
        except ValueError as exc:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.EXCHANGE_FILTER_VIOLATION,
                explanation=str(exc),
            )

        return RiskCheckResult(
            is_approved=True,
            explanation="All risk invariants satisfied for entry",
            approved_intent=intent,
        )

    def evaluate_dca(
        self,
        decision: DecisionSnapshot,
        current_price: Decimal,
        account_state: AccountRiskState,
        requested_notional: Decimal,
    ) -> RiskCheckResult:
        """Evaluate prospective DCA addition enforcing the $500 hard limit."""
        # 1. Decision must be BUY or ADD
        if decision.decision_state not in {DecisionState.BUY, DecisionState.ADD}:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.DECISION_NOT_ACTIONABLE,
                explanation=f"Decision state {decision.decision_state} not actionable for DCA",
            )

        # 2. Hard individual DCA ceiling
        if requested_notional > MAX_DCA_NOTIONAL:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.EXCEEDS_DCA_NOTIONAL_LIMIT,
                explanation=(
                    f"Requested DCA notional (${requested_notional:.2f}) "
                    f"exceeds hard ceiling of ${MAX_DCA_NOTIONAL:.2f}"
                ),
            )

        # 3. Maximum entries limit
        if account_state.open_entries_count >= self.config.max_entries:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.EXCEEDS_MAX_ENTRIES,
                explanation=(
                    f"Open entries ({account_state.open_entries_count}) "
                    f"already at max ({self.config.max_entries})"
                ),
            )

        # 4. Realized daily loss limit
        if self.config.max_daily_loss is not None:
            if account_state.realized_daily_loss >= self.config.max_daily_loss:
                return RiskCheckResult(
                    is_approved=False,
                    rejection_reason=RiskRejectionReason.EXCEEDS_DAILY_LOSS_LIMIT,
                    explanation="Realized daily loss limit reached",
                )

        # 5. Maximum total exposure limit
        if self.config.max_total_exposure is not None:
            projected_exposure = account_state.total_open_exposure + requested_notional
            if projected_exposure > self.config.max_total_exposure:
                return RiskCheckResult(
                    is_approved=False,
                    rejection_reason=RiskRejectionReason.EXCEEDS_MAX_EXPOSURE,
                    explanation=(
                        f"Projected exposure (${projected_exposure:.2f}) "
                        f"exceeds limit (${self.config.max_total_exposure:.2f})"
                    ),
                )

        # 6. Sizing and filter validation
        try:
            client_id = f"DCA_{uuid.uuid4().hex[:8]}"
            intent = self.sizer.create_dca_intent(
                price=current_price,
                requested_notional=requested_notional,
                client_order_id=client_id,
                reason=decision.reason,
            )
        except ValueError as exc:
            return RiskCheckResult(
                is_approved=False,
                rejection_reason=RiskRejectionReason.EXCHANGE_FILTER_VIOLATION,
                explanation=str(exc),
            )

        return RiskCheckResult(
            is_approved=True,
            explanation="All risk invariants satisfied for DCA",
            approved_intent=intent,
        )
