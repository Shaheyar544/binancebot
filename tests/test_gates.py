"""Tests for live execution gates and safety invariants."""

import pytest

from src.config.settings import ExecutionGateConfig


def test_default_execution_gates_are_disabled() -> None:
    """Execution gates must default to False (disabled)."""
    gates = ExecutionGateConfig()
    assert gates.live_trading is False
    assert gates.enable_order_execution is False
    assert gates.can_execute_live is False


def test_live_execution_raises_when_disabled() -> None:
    """Attempting live execution with default/disabled gates must raise RuntimeError."""
    gates = ExecutionGateConfig()
    with pytest.raises(RuntimeError, match="Live order execution is strictly blocked"):
        gates.assert_live_execution_allowed()


@pytest.mark.parametrize(
    ("live_trading", "enable_order_execution"),
    [
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_live_execution_requires_both_flags(
    live_trading: bool, enable_order_execution: bool
) -> None:
    """Both live_trading and enable_order_execution must be True."""
    gates = ExecutionGateConfig(
        live_trading=live_trading,
        enable_order_execution=enable_order_execution,
    )
    assert gates.can_execute_live is False
    with pytest.raises(RuntimeError, match="Live order execution is strictly blocked"):
        gates.assert_live_execution_allowed()


def test_live_execution_allowed_only_when_both_true() -> None:
    """When both flags are True, live execution is permitted."""
    gates = ExecutionGateConfig(live_trading=True, enable_order_execution=True)
    assert gates.can_execute_live is True
    # Should not raise
    gates.assert_live_execution_allowed()
