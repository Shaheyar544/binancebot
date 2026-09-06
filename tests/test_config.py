"""Tests for user risk configuration and liquidation safety validation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.config.settings import BotConfig, UserRiskConfig


def test_required_risk_settings_must_be_provided() -> None:
    """Allocated funds, leverage, and max acceptable liquidation price are mandatory."""
    with pytest.raises(ValidationError) as exc_info:
        UserRiskConfig()  # type: ignore[call-arg]

    errors = str(exc_info.value)
    assert "allocated_funds" in errors
    assert "leverage" in errors
    assert "max_acceptable_liquidation_price" in errors


def test_user_config_values_are_immutable() -> None:
    """User risk configuration cannot be mutated after creation."""
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("5.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    with pytest.raises(ValidationError):
        setattr(config, "leverage", Decimal("10.0"))


def test_invalid_negative_or_zero_values_rejected() -> None:
    """Allocated funds, leverage, and max liquidation price must be positive."""
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


def test_incompatible_liquidation_price_rejected() -> None:
    """If leverage causes estimated liquidation above max acceptable liquidation price, reject."""
    # With reference entry price ~2700, 10x leverage puts long liquidation ~2440.
    # If the user requires max acceptable liquidation price of 2000 (demanding safety down to 2000),
    # an estimated liquidation at 2440 is incompatible and must be rejected.
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("10.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    reference_entry_price = Decimal("2700.00")
    with pytest.raises(ValueError, match="Incompatible risk configuration: Estimated liquidation"):
        config.validate_liquidation_compatibility(reference_entry_price)


def test_compatible_liquidation_price_passes() -> None:
    """Compatible liquidation configuration passes without altering values."""
    # With entry ~2700 and 2x leverage, liquidation is ~1350, well below 2000.
    config = UserRiskConfig(
        allocated_funds=Decimal("1000.00"),
        leverage=Decimal("2.0"),
        max_acceptable_liquidation_price=Decimal("2000.00"),
    )
    reference_entry_price = Decimal("2700.00")
    est_liq = config.validate_liquidation_compatibility(reference_entry_price)
    assert est_liq <= Decimal("2000.00")
    # Verify values remained intact
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
