"""Tests for PreFlightChecker: 10-point safety invariant validation."""

from decimal import Decimal

from src.config.settings import BotConfig, ExecutionGateConfig, UserRiskConfig
from src.paper.preflight import PreFlightChecker


def test_preflight_checker_all_invariants_pass() -> None:
    """Pre-flight checker validates all 10 safety invariants."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("5000.00"),
    )
    # Default disabled live execution
    config = BotConfig(
        gates=ExecutionGateConfig(live_trading=False, enable_order_execution=False),
        risk=user_risk,
    )

    checker = PreFlightChecker(config=config)
    report = checker.evaluate()

    # All safety invariant checks must pass
    assert report.is_ready_for_paper is True
    # Crucial invariant: is_ready_for_live must be False when live gates are disabled
    assert report.is_ready_for_live is False
    assert report.checklist_results["live_gates_disabled"] is True
    assert report.checklist_results["dca_ceiling_valid"] is True
    assert report.checklist_results["liquidation_safe"] is True


def test_preflight_checker_detects_live_gates_enabled() -> None:
    """If live gates are enabled, live_gates_disabled check fails."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=Decimal("200.00"),
        emergency_loss_limit=Decimal("400.00"),
        max_total_exposure=Decimal("5000.00"),
    )
    config = BotConfig(
        gates=ExecutionGateConfig(live_trading=True, enable_order_execution=True),
        risk=user_risk,
    )
    checker = PreFlightChecker(config=config)
    report = checker.evaluate()

    # Safety check fails because live_gates_disabled is False
    assert report.checklist_results["live_gates_disabled"] is False
    assert report.is_ready_for_paper is False
    assert report.is_ready_for_live is False


def test_preflight_checker_missing_optional_risk_parameters() -> None:
    """Missing daily loss or exposure limits fails preflight invariant evaluation."""
    user_risk = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2500.00"),
        max_entries=3,
        max_daily_loss=None,
        emergency_loss_limit=None,
        max_total_exposure=None,
    )
    config = BotConfig(
        gates=ExecutionGateConfig(live_trading=False, enable_order_execution=False),
        risk=user_risk,
    )
    checker = PreFlightChecker(config=config)
    report = checker.evaluate()

    assert report.checklist_results["daily_loss_configured"] is False
    assert report.checklist_results["emergency_loss_configured"] is False
    assert report.checklist_results["exposure_limit_configured"] is False
    assert report.is_ready_for_paper is False
    assert report.is_ready_for_live is False
