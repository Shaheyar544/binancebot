"""Tests for user risk configuration and liquidation safety validation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.config.settings import BotConfig, UserRiskConfig
from src.domain.interfaces import LiquidationEstimator


class MockLiquidationEstimator:
    """Deterministic mock estimator for unit testing."""

    def __init__(self, mocked_price: Decimal) -> None:
        self.mocked_price = mocked_price

    def estimate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        allocated_funds: Decimal,
    ) -> Decimal:
        return self.mocked_price


def test_required_risk_settings_must_be_provided() -> None:
    """Allocated funds, leverage, and max acceptable liquidation price are mandatory."""
    with pytest.raises(ValidationError) as exc_info:
        UserRiskConfig()  # type: ignore[call-arg]

    errors = str(exc_info.value)
    assert "allocated_funds" in errors
    assert "leverage" in errors
    assert "max_acceptable_liquidation_price" in errors


def test_financial_precision_uses_decimal() -> None:
    """Financial parameters must strictly be Decimals and not floats."""
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    assert isinstance(config.allocated_funds, Decimal)
    assert isinstance(config.leverage, Decimal)
    assert isinstance(config.max_acceptable_liquidation_price, Decimal)


def test_user_config_values_are_immutable() -> None:
    """User risk configuration cannot be mutated after construction."""
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    with pytest.raises(ValidationError):
        config.leverage = Decimal("10.0")
    with pytest.raises(ValidationError):
        config.allocated_funds = Decimal("2000.00")
    with pytest.raises(ValidationError):
        config.max_acceptable_liquidation_price = Decimal("1500.00")


def test_invalid_negative_or_zero_values_rejected() -> None:
    """Allocated funds, leverage, and max liquidation price must be positive and valid."""
    with pytest.raises(ValidationError):
        UserRiskConfig(
            allocated_funds=Decimal("0.00"),
            leverage=Decimal("5.0"),
            max_acceptable_liquidation_price=Decimal("2000.00"),
        )
    with pytest.raises(ValidationError):
        UserRiskConfig(
            allocated_funds=Decimal("1000.00"),
            leverage=Decimal("0.5"),  # Leverage must be >= 1.0
            max_acceptable_liquidation_price=Decimal("2000.00"),
        )
    with pytest.raises(ValidationError):
        UserRiskConfig(
            allocated_funds=Decimal("1000.00"),
            leverage=Decimal("5.0"),
            max_acceptable_liquidation_price=Decimal("-100.00"),
        )


def test_incompatible_liquidation_price_rejected_via_protocol() -> None:
    """When estimated liquidation price > max acceptable liquidation price, reject."""
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("10.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    # Mock estimator returning 2350.00 (which exceeds acceptable 2000.00)
    incompatible_estimator: LiquidationEstimator = MockLiquidationEstimator(Decimal("2350.00"))

    with pytest.raises(ValueError, match="Incompatible risk configuration: Estimated liquidation"):
        config.validate_liquidation_safety(incompatible_estimator, Decimal("2700.00"))

    # Direct validation of estimated price also rejects
    with pytest.raises(ValueError, match="exceeds user maximum acceptable liquidation price"):
        config.validate_estimated_liquidation(Decimal("2350.00"))

    # User values must NOT have been changed to make it pass
    assert config.allocated_funds == Decimal("1000.00")
    assert config.leverage == Decimal("10.0")
    assert config.max_acceptable_liquidation_price == Decimal("2000.00")


def test_compatible_liquidation_price_passes_via_protocol() -> None:
    """Compatible liquidation configuration passes without altering values."""
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    # Mock estimator returning 1350.00 (which is safely below 2000.00)
    compatible_estimator: LiquidationEstimator = MockLiquidationEstimator(Decimal("1350.00"))

    est_liq = config.validate_liquidation_safety(compatible_estimator, Decimal("2700.00"))
    assert est_liq == Decimal("1350.00")

    # Direct validation of compatible price
    config.validate_estimated_liquidation(Decimal("1350.00"))

    # Values must remain identical
    assert config.allocated_funds == Decimal("1000.00")
    assert config.leverage == Decimal("2.0")
    assert config.max_acceptable_liquidation_price == Decimal("2000.00")


def test_bot_config_loads_safely() -> None:
    """BotConfig aggregates execution gates and risk config safely."""
    bot_cfg = BotConfig(
        risk=UserRiskConfig(
            allocated_funds=Decimal("1000.00"),
            leverage=Decimal("3.0"),
            max_acceptable_liquidation_price=Decimal("1800.00"),
        )
    )
    assert bot_cfg.gates.live_trading is False
    assert bot_cfg.gates.enable_order_execution is False
    assert bot_cfg.risk.allocated_funds == Decimal("1000.00")
