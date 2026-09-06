"""Tests for RiskEngine: authority hierarchy, invariant checks, and liquidation safety."""

from decimal import Decimal

import pytest

from src.config.settings import UserRiskConfig
from src.domain.enums import DecisionState, MarketRegime
from src.domain.models import DecisionSnapshot, PositionSnapshot
from src.exchange.metadata import SymbolFilters
from src.risk.engine import RiskEngine
from src.risk.models import AccountRiskState, RiskRejectionReason


class StubLiquidationEstimator:
    """Deterministic liquidation estimator stub for testing."""

    def __init__(self, liq_price: Decimal) -> None:
        self.liq_price = liq_price

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal:
        return self.liq_price


@pytest.fixture
def xau_filters() -> SymbolFilters:
    return SymbolFilters(
        symbol="XAUUSDT",
        status="TRADING",
        contract_type="PERPETUAL",
        base_asset="XAU",
        quote_asset="USDT",
        price_precision=2,
        quantity_precision=3,
        tick_size=Decimal("0.01"),
        min_price=Decimal("100.00"),
        max_price=Decimal("100000.00"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        max_qty=Decimal("1000.000"),
        min_notional=Decimal("5.0"),
    )


@pytest.fixture
def base_user_config() -> UserRiskConfig:
    return UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("5000.00"),
    )


@pytest.fixture
def healthy_account_state() -> AccountRiskState:
    return AccountRiskState(
        wallet_balance=Decimal("1000.00"),
        available_balance=Decimal("1000.00"),
        total_open_exposure=Decimal("0.0"),
        realized_daily_loss=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        open_entries_count=0,
    )


@pytest.fixture
def candidate_buy_decision() -> DecisionSnapshot:
    return DecisionSnapshot(
        decision_id="DEC_BUY_001",
        symbol="XAUUSDT",
        timestamp=1700000000000,
        decision_state=DecisionState.BUY,
        regime=MarketRegime.STRONG_BULL,
        reason="High conviction technical setup",
    )


def test_user_risk_parameters_never_silently_changed(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    healthy_account_state: AccountRiskState,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """User risk parameters must remain exactly identical before and after risk evaluation."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    orig_funds = base_user_config.allocated_funds
    orig_lev = base_user_config.leverage
    orig_max_liq = base_user_config.max_acceptable_liquidation_price

    res = engine.evaluate_entry(
        decision=candidate_buy_decision,
        current_price=Decimal("2700.00"),
        account_state=healthy_account_state,
        target_notional=Decimal("1000.00"),
    )

    assert res.is_approved is True
    assert base_user_config.allocated_funds == orig_funds
    assert base_user_config.leverage == orig_lev
    assert base_user_config.max_acceptable_liquidation_price == orig_max_liq


def test_unsafe_liquidation_price_rejected(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    healthy_account_state: AccountRiskState,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """If estimated liquidation price > max_acceptable_liquidation_price, reject trade."""
    # User allows max $2500.00 liquidation; estimator returns $2550.00 (too close to price)
    estimator = StubLiquidationEstimator(liq_price=Decimal("2550.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    res = engine.evaluate_entry(
        decision=candidate_buy_decision,
        current_price=Decimal("2700.00"),
        account_state=healthy_account_state,
        target_notional=Decimal("1000.00"),
    )

    assert res.is_approved is False
    assert res.rejection_reason == RiskRejectionReason.UNSAFE_LIQUIDATION_PRICE
    assert "exceeds acceptable threshold" in res.explanation


def test_exceeding_daily_loss_limit_rejected(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """When realized daily loss >= max_daily_loss, new entries are blocked."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    account_state = AccountRiskState(
        wallet_balance=Decimal("800.00"),
        available_balance=Decimal("800.00"),
        total_open_exposure=Decimal("0.0"),
        realized_daily_loss=Decimal("250.00"),  # Exceeds max_daily_loss of $200.00
        unrealized_pnl=Decimal("0.0"),
        open_entries_count=0,
    )

    res = engine.evaluate_entry(
        decision=candidate_buy_decision,
        current_price=Decimal("2700.00"),
        account_state=account_state,
        target_notional=Decimal("1000.00"),
    )

    assert res.is_approved is False
    assert res.rejection_reason == RiskRejectionReason.EXCEEDS_DAILY_LOSS_LIMIT


def test_exceeding_max_exposure_rejected(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """When new order would breach max_total_exposure, reject trade."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    account_state = AccountRiskState(
        wallet_balance=Decimal("1000.00"),
        available_balance=Decimal("1000.00"),
        total_open_exposure=Decimal("4500.00"),  # max is $5000.00
        realized_daily_loss=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        open_entries_count=1,
    )

    # Adding $1000.00 notional would make exposure $5500.00 > $5000.00
    res = engine.evaluate_entry(
        decision=candidate_buy_decision,
        current_price=Decimal("2700.00"),
        account_state=account_state,
        target_notional=Decimal("1000.00"),
    )

    assert res.is_approved is False
    assert res.rejection_reason == RiskRejectionReason.EXCEEDS_MAX_EXPOSURE


def test_dca_ceiling_strictly_enforced(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    healthy_account_state: AccountRiskState,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """DCA notional > $500.00 is rejected by RiskEngine."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    # 1. $500.00 DCA -> Approved
    res_ok = engine.evaluate_dca(
        decision=candidate_buy_decision,
        current_price=Decimal("2680.00"),
        account_state=healthy_account_state,
        requested_notional=Decimal("500.00"),
    )
    assert res_ok.is_approved is True
    assert res_ok.approved_intent is not None
    assert res_ok.approved_intent.is_dca is True
    assert res_ok.approved_intent.notional <= Decimal("500.00")

    # 2. $500.01 DCA -> Rejected
    res_fail = engine.evaluate_dca(
        decision=candidate_buy_decision,
        current_price=Decimal("2680.00"),
        account_state=healthy_account_state,
        requested_notional=Decimal("500.01"),
    )
    assert res_fail.is_approved is False
    assert res_fail.rejection_reason == RiskRejectionReason.EXCEEDS_DCA_NOTIONAL_LIMIT


def test_dca_max_entries_enforced(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
    candidate_buy_decision: DecisionSnapshot,
) -> None:
    """When entries reach max_entries, further DCA additions are blocked."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    account_state = AccountRiskState(
        wallet_balance=Decimal("1000.00"),
        available_balance=Decimal("1000.00"),
        total_open_exposure=Decimal("1500.00"),
        realized_daily_loss=Decimal("0.0"),
        unrealized_pnl=Decimal("0.0"),
        open_entries_count=3,  # Already at max_entries=3
    )

    res = engine.evaluate_dca(
        decision=candidate_buy_decision,
        current_price=Decimal("2680.00"),
        account_state=account_state,
        requested_notional=Decimal("400.00"),
    )
    assert res.is_approved is False
    assert res.rejection_reason == RiskRejectionReason.EXCEEDS_MAX_ENTRIES


def test_emergency_loss_trigger(
    base_user_config: UserRiskConfig,
    xau_filters: SymbolFilters,
) -> None:
    """When unrealized loss breaches emergency threshold, trigger emergency exit."""
    estimator = StubLiquidationEstimator(liq_price=Decimal("2400.00"))
    engine = RiskEngine(config=base_user_config, filters=xau_filters, estimator=estimator)

    pos = PositionSnapshot(
        symbol="XAUUSDT",
        size=Decimal("1.0"),
        entry_price=Decimal("2700.00"),
        leverage=Decimal("5.0"),
        margin=Decimal("540.00"),
        liquidation_price=Decimal("2400.00"),
        unrealized_pnl=Decimal("-450.00"),  # Breaches emergency_loss_limit ($400)
    )

    is_emergency = engine.is_emergency_loss_breached(pos)
    assert is_emergency is True
